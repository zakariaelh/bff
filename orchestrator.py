import json
import io
import random
import re
import struct
import time
import traceback
from datetime import datetime
from queue import Queue
from queue import Empty

from search import SearchIndexer
from services.mock_ai_service import MockAIService
from scenes.story_page_async_scene import StoryPageAsyncScene

from scenes.story_grandma_scene import StoryGrandmaScene
from scenes.stop_listening_scene import StopListeningScene
from scenes.start_listening_scene import StartListeningScene

from threading import Thread

from constants import FRIENDLY_PROMPT, ROASTER_PROMT, COMPLIMENT_PROMPT

import base64
# Function to encode the image



# Path to your image
image_path = "/Users/zakariaelhjouji/Downloads/hi1.png"

latest_roasts = "Your head is shaped like a pear."

class Orchestrator():
    def __init__(self, image_setter, microphone, ai_tts_service, ai_image_gen_service, ai_llm_service, roast_llm, story_id, logger, compliment_llm):
        self.image_setter = image_setter
        self.microphone = microphone

        self.ai_tts_service = ai_tts_service
        self.ai_image_gen_service = ai_image_gen_service
        self.ai_llm_service = ai_llm_service
        self.roast_llm = roast_llm
        self.compliment_llm = compliment_llm

        self.search_indexer = SearchIndexer(story_id)

        self.tts_getter = None
        self.image_getter = None

        self.messages = [{"role": "system", "content": FRIENDLY_PROMPT}]

        # self.roast_system_message = [{"role": "system", "content": "You're the best roaster ever! Come up with 5 clever roasts."}]
        self.roast_system_message = [{"role": "system", "content": ROASTER_PROMT}]
        self.compliment_system_message = [{"role": "system", "content": COMPLIMENT_PROMPT}]
        
        self.initial_message = "Hey there, what's up!"
        self.roasts = None
        self.compliments = None

        self.llm_response_thread = None

        self.scene_queue = Queue()
        self.stop_threads = False
        self.started_listening_at = None
        self.image_this_time = True
        self.story_sentences = []

        self.logger = logger



    def handle_user_speech(self, user_speech):
        # self.logger.info(f"👅 Handling user speech: {user_speech}")
        if not self.llm_response_thread or not self.llm_response_thread.is_alive():
            self.enqueue(StopListeningScene)
            self.llm_response_thread = Thread(target=self.request_llm_response, args=(user_speech,))
            self.llm_response_thread.start()
        else:
            self.logger.info("discarding overlapping speech, TODO barge-in")

    def start_listening(self):
        self.started_listening_at = datetime.now()

    def stop_listening(self):
        self.started_listening_at = None

    def listening_since(self):
        return self.started_listening_at

    def request_llm_response(self, user_speech):
        try:
            message = f"""
                User speech:
                {user_speech}
            """
            rd = random.random()
            if rd > 0.5:
                if rd > 0.75 and self.roasts:
                    message += f"""
                        Possible roasts you can use:
                        {self.roasts}
                    """
                    self.roasts = None
                elif rd < 0.75 and self.compliments:
                    message += f"""
                        Possible compliments you can use:
                        {self.compliments}
                    """
                    self.compliments = None

            self.messages.append({
                "role": "user", 
                "content": message
                })
            response = self.ai_llm_service.run_llm(self.messages)
            self.handle_llm_response(response)
        except Exception as e:
            self.logger.error(f"Exception in request_llm_response: {e}")

    def request_intro(self):
        return self.ai_tts_service.run_tts(self.initial_message)

    def request_roast(self, b64image):
        resp = self.roast_llm.run_llm(
            self.roast_system_message, b64image=b64image, stream=False)
        self.roasts = resp.choices[0].message.content
        print('ROAASTTSSS ------- ', self.roasts)

    def request_compliment(self, b64image):
        resp = self.compliment_llm.run_llm(
            self.compliment_system_message, b64image=b64image, stream=False)
        self.compliments = resp.choices[0].message.content
        print('COMPLIMENTS ------- ', self.compliments)
    
    def handle_llm_response(self, llm_response):
        out = ''
        full_response = ''
        prompt_started = False
        for chunk in llm_response:
            if len(chunk.choices) == 0:
                continue
            if chunk.choices[0].delta.content:
                if chunk.choices[0].delta.content != {}: #streaming a content chunk
                    next_chunk = chunk.choices[0].delta.content
                    out += next_chunk
                    full_response += next_chunk

                    #if re.match(r'^.*[.!?]$', out): # it looks like a sentence
                    if prompt_started == False:
                        if re.findall(r'.*\[[sS]tart\].*', out):
                            # Then we have the intro. Send it to speech ASAP
                            out = out.replace("[Start]", "")
                            out = out.replace("[start]", "")

                            out = out.replace("\n", " ")
                            if len(out) > 2:
                                self.enqueue(StoryGrandmaScene, sentence=out)
                            out = ''

                        elif re.findall(r'.*\[[bB]reak\].*', out):
                            # Then it's a page of the story. Get an image too
                            out = out.replace("[Break]", "")
                            out = out.replace("[break]", "")
                            out = out.replace("\n", " ")
                            if len(out) > 2:
                                self.story_sentences.append(out)
                                self.enqueue(StoryPageAsyncScene, sentence=out, image=self.image_this_time, story_sentences=self.story_sentences.copy())

                                self.image_this_time = not self.image_this_time

                            out = ''
                        elif re.findall(r'.*\[[pP]rompt\].*', out):
                            # Then it's question time. Flush any
                            # text here as a story page, then set
                            # the var to get to prompt mode
                            #cb: trying scene now
                            # self.handle_chunk(out)
                            out = out.replace("[Prompt]", "")
                            out = out.replace("[prompt]", "")

                            out = out.replace("\n", " ")
                            if len(out) > 2:
                                self.story_sentences.append(out)
                                self.enqueue(StoryPageAsyncScene, sentence=out, image=self.image_this_time, story_sentences=self.story_sentences.copy())
                                self.image_this_time =  not self.image_this_time

                            out = ''
                    else:
                        # Just get the rest of the output as the prompt
                        pass


                        out = ''
        # get the last one too; it should be the prompt
        self.logger.info(f"🎬 FINAL Out: {out}")
        self.enqueue(StoryGrandmaScene, sentence=out)
        self.enqueue(StartListeningScene)
        self.logger.info(f"🎬 FULL MESSAGE: {full_response}")
        self.messages.append({"role": "assistant", "content": full_response})
        self.image_this_time = False

    def handle_chunk(self, chunk):
        #self.llm_history.append(chunk)

        self.tts_getter = Thread(target=self.request_tts, args=(chunk,))
        self.tts_getter.start()
        self.image_getter = Thread(target=self.request_image, args=(chunk,))
        self.image_getter.start()

        self.tts_getter.join()
        self.image_getter.join()

    def request_tts(self, text):
        try:
            for chunk in self.ai_tts_service.run_tts(text):
                yield chunk
        except Exception as e:
            self.logger.error(f"Exception in request_tts: {e}")

    def request_image(self, text):
        try:
            (url, image) = self.ai_image_gen_service.run_image_gen(text)
            return (url, image)
        except Exception as e:
            self.logger.error(f"Exception in request_image: {e}")

    def handle_video_frame(self, b64frame):
        self.llm_roast_thread = Thread(target=self.request_roast, args=(b64frame,))
        self.llm_roast_thread.start()
        self.llm_compliment_thread = Thread(target=self.request_compliment, args=(b64frame,))
        self.llm_compliment_thread.start()
    
    def request_image_description(self, story_sentences):
        if len(self.story_sentences) == 1:
            prompt = f"You are an illustrator for a children's story book. Generate a prompt for DALL-E to create an illustration for the first page of the book, which reads: \"{self.story_sentences[0]}\"\n\n Your response should start with the phrase \"Children's book illustration of\"."
        else:
            prompt = f"You are an illustrator for a children's story book. Here is the story so far:\n\n\"{' '.join(self.story_sentences[:-1])}\"\n\nGenerate a prompt for DALL-E to create an illustration for the next page. Here's the sentence for the next page:\n\n\"{self.story_sentences[-1:][0]}\"\n\n Your response should start with the phrase \"Children's book illustration of\"."

        #prompt += " Children's story book illustration"
        self.logger.info(f"🎆 Prompt: {prompt}")
        msgs = [{"role": "system", "content": prompt}]
        start = time.time()
        img_response = self.ai_llm_service.run_llm(msgs, stream = False)
        image_prompt = img_response['choices'][0]['message']['content']
        # It comes back wrapped in quotes for some reason
        image_prompt = re.sub(r'^"', '', image_prompt)
        image_prompt = re.sub(r'"$', '', image_prompt)
        self.logger.info(f"🎆 Resulting image prompt: {image_prompt}")
        self.logger.info(f"==== time to run llm for image generation {time.time() - start}")
        return image_prompt

    def handle_audio(self, audio):
        self.logger.info("!!! Starting speaking")
        start = time.time()
        b = bytearray()
        final = False
        smallest_write_size = 3200
        try:
            for chunk in audio:
                b.extend(chunk)
                l = len(b) - (len(b) % smallest_write_size)
                if l:
                    self.microphone.write_frames(bytes(b[:l]))
                    b = b[l:]

            if len(b):
                self.microphone.write_frames(bytes(b))
        except Exception as e:
            self.logger.error(f"Exception in handle_audio: {e}")
        finally:
            self.logger.info(f"!!! Finished speaking in {time.time() - start} seconds")

    def display_image(self, image):
        if self.image_setter:
            self.image_setter.set_image(image)

    def enqueue(self, scene_type, **kwargs):
        # Take the newly created scene object, call its prepare function, and queue it to perform
        kwargs['orchestrator'] = self
        kwargs['logger'] = self.logger
        self.scene_queue.put(scene_type(**kwargs))
        pass

    def action(self):
        # start playing scenes. This allows us to prepare scenes
        # before we actually start playback
        self.playback_thread = Thread(target=self.playback)
        self.playback_thread.start()

    def index_scene_async(self, scene):
        self.search_indexer.index_text(scene.sentence)
        if 'url' in scene.scene_data:
            self.search_indexer.index_image(scene.scene_data['url'])

    def index_scene(self, scene):
        if 'sentence' in scene.__dict__:
            thread = Thread(target=self.index_scene_async, args=(scene,))
            thread.start()
            # we let this thread run unattended

    def playback(self):
        while True:
            try:
                if self.stop_threads:
                    self.logger.info("🎬 Shutting down playback thread")
                    break
                scene = self.scene_queue.get(block=False)
                if 'sentence' in scene.__dict__:
                    self.logger.info(f"🎬 Performing scene: {type(scene).__name__}, {scene.sentence}")
                else:
                    self.logger.info(f"🎬 Performing sentenceless scene: {type(scene).__name__}")
                scene.perform()
            except Empty:
                time.sleep(0.1)
                continue
