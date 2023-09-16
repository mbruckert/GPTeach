from typing import Sequence
import os
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "shellhacks-2023-042c64c6e9eb.json"
import google.cloud.texttospeech as tts
from typing import List
from langchain.llms import OpenAI
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain.pydantic_v1 import BaseModel, Field, validator
from typing import List
from langchain import PromptTemplate
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.chat_models import ChatOpenAI
from dotenv import load_dotenv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydub import AudioSegment
from moviepy.editor import *
import uuid
from google.cloud import storage

load_dotenv()
chat = ChatOpenAI(model="gpt-4")
bucket_name = "shellhacks-2023"

class Scene(BaseModel):
    visuals: str
    audio: str

class Storyboard(BaseModel):
    scenes: List[Scene]

def generate_video_segment(segment: int, scene: Scene):
    # set up tts voice
    voice_name = "en-US-Studio-M"
    language_code = "-".join(voice_name.split("-")[:2])
    text_input = tts.SynthesisInput(text=scene.audio)
    voice_params = tts.VoiceSelectionParams(
        language_code=language_code, name=voice_name
    )
    audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16)

    # generate audio
    client = tts.TextToSpeechClient()
    response = client.synthesize_speech(
        input=text_input,
        voice=voice_params,
        audio_config=audio_config,
    )

    # save audio and get length in seconds
    filename = f"{voice_name}_{segment}.wav"
    with open(filename, "wb") as out:
        out.write(response.audio_content)
        print(f'Generated speech saved to "{filename}"')
    audio = AudioSegment.from_wav(filename)
    duration_seconds = len(audio) / 1000
    
    # generate visuals
    scene_template=f"""Based on the user's prompt, fill out the template below with manim code to generate the desired visuals. The visuals should last {duration_seconds} seconds long.

Note that some aspects of manim have changed since you last used it. Here are the changes you need to make:
ShowCreation -> Create

Only return the code.

from manim import *

class VideoVisual_{segment}(Scene):
    def construct(self):
        YOUR CODE HERE

if frame == "main":
    from manim import config

    config.pixel_height = 1080
    config.pixel_width = 1920

    scene = VideoVisual_{segment}()
    scene.render()"""

    scene_chat_prompt = ChatPromptTemplate.from_messages([
        ("system", scene_template),
        ("human", "{prompt}")
    ])

    segment_generated = False
    retries = 0

    while not segment_generated:
        manim_code = chat(scene_chat_prompt.format_messages(prompt=scene.visuals)).content

        with open(f"exec_test_{segment}.py", 'w') as pyfile:
            pyfile.write(manim_code)

        os.system(f"python exec_test_{segment}.py")

        if os.path.isfile(f"media/videos/1080p60/VideoVisual_{segment}.mp4"):
            segment_generated = True
        else:
            retries += 1

        if retries > 5:
            raise Exception("Unable to generate video segment")

    # overlay audio onto video
    video = VideoFileClip(f"media/videos/1080p60/VideoVisual_{segment}.mp4")
    audio = AudioFileClip(filename)

    # Set the audio of the video to the provided audio
    final_video = video.set_audio(audio)
    
    # Write the result to a file
    final_video.write_videofile(f"final_{segment}.mp4", codec='libx264')

def main(request):
    # handle CORS preflight
    # if request.method == 'OPTIONS':
    #     headers = {
    #         'Access-Control-Allow-Origin': '*',
    #         'Access-Control-Allow-Methods': 'GET',
    #         'Access-Control-Allow-Headers': 'Content-Type',
    #         'Access-Control-Max-Age': '3600'
    #     }

    #     return ('', 204, headers)

    # set CORS return headers
    cors_headers = {
        'Access-Control-Allow-Origin': '*'
    }

    # req_body = request.get_json()
    # user_request = req_body['request']

    user_request = request

    # generate storyboard
    template="Can you generate a concise storyboard that helps to explain the following concept/answer the provided question in the style of a khan academy video. Use examples including latex, graphs, animations, charts, and more. Make it as visual as possible. Only include enough information to be able to replicate you vision, the bare minimum description. Your storyboard can include anything possible in manim. You should not exceed 5 scenes. You should answer in the following format: {formatting_instructions}"
    system_message_prompt = SystemMessagePromptTemplate.from_template(template)
    human_template="{text}"
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])

    parser = PydanticOutputParser(pydantic_object=Storyboard)

    storyboard = parser.parse(chat(chat_prompt.format_prompt(formatting_instructions=parser.get_format_instructions(), text=user_request).to_messages()).content)
    segments, scenes = zip(*enumerate(storyboard.scenes))

    # generate video segments
    with ThreadPoolExecutor(10) as executor:
        executor.map(generate_video_segment, segments, scenes)

    # concatenate the video segments
    final_video = concatenate_videoclips([VideoFileClip(f"final_{segment}.mp4") for segment in segments])

    # output the video
    final_video.write_videofile("final.mp4", codec='libx264')

    # upload the video to cloud storage and return the download link
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(f"{uuid.uuid4()}.mp4")
    blob.upload_from_filename("final.mp4")
    video_url = blob.public_url

    return (video_url, 200, cors_headers)


main("Explain the concept of curl in calculus three")
