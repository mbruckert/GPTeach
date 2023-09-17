import ast
import re
from typing import Sequence
import os
import shutil
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "shellhacks-2023-042c64c6e9eb.json"
import google.cloud.texttospeech as tts
from typing import List
from langchain.llms import OpenAI
from langchain.output_parsers import PydanticOutputParser, OutputFixingParser
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
from flask import Flask, request, jsonify
from flask_cors import CORS
from langchain.chat_models import ChatOpenAI
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.chains import RetrievalQA
from dotenv import load_dotenv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from pydub import AudioSegment
from moviepy.editor import *
import uuid
from google.cloud import storage

load_dotenv()
app = Flask(__name__)
CORS(app)
chat = ChatOpenAI(model="gpt-4")
vectorstore = Chroma(persist_directory="manim_vectorstore", embedding_function=OpenAIEmbeddings())
bucket_name = "shellhacks-2023"

class Scene(BaseModel):
    visuals: str = Field(..., description="Description of the visuals to accompany the script. These visuals can be anything possible in manim")
    audio: str = Field(..., description="Script for this scene. Include what you want the narrator to say.")

class Storyboard(BaseModel):
    scenes: List[Scene]
    
class CodeResponse(BaseModel):
    code: str = Field(..., description="Manim code that generates the visuals for the scene. This field MUST be pure python code, that could be put in its own file and executed as-is.")

    @validator("code")
    def is_code(cls, v):
        try:
            parsed_module = ast.parse(v)
            class_names = [node.name for node in ast.walk(parsed_module) if isinstance(node, ast.ClassDef)]
            if not any(["VideoVisual_" in name for name in class_names]):
                raise ValueError("Class name does not match template")
        except SyntaxError:
            raise ValueError("Code is not valid Python")
        return v

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
    parser = PydanticOutputParser(pydantic_object=CodeResponse)
    fixing_parser = OutputFixingParser.from_llm(parser=parser, llm=chat)

    prompt_template = """Using the information below, fill in and return the TEMPLATE below to generate the visuals REQUESTED by the user. The code you return will then be executed in a standalone file, SO IT MUST BE CORRECT AND COMPLETE.

FORMAT:
{format_instructions}

DOCUMENTATION:
{context}
Always use ArrowVectorStore instead of VectorStore for vector fields.

TEMPLATE:
```
from manim import *

class VideoVisual_"""+str(segment)+"""(Scene):
    def construct(self):
        [WRITE YOUR CODE TO PRODUCE THE REQUESTED VISUALS HERE]

if frame == "main":
    from manim import config

    config.pixel_height = 1080
    config.pixel_width = 1920

    scene = VideoVisual_"""+str(segment)+"""()
    scene.render()
```

REQUEST: 
{question}

ANSWER (PYTHON CODE ONLY, NO OTHER TEXT OR COMMENTARY OR MARKDOWN):"""
    PROMPT = PromptTemplate(
        template=prompt_template, input_variables=["context", "question"], partial_variables={"format_instructions": parser.get_format_instructions()}
    )
    chain_type_kwargs = {"prompt": PROMPT}
    qa_chain = RetrievalQA.from_chain_type(llm=chat, chain_type="stuff", retriever=vectorstore.as_retriever(), chain_type_kwargs=chain_type_kwargs)

    segment_generated = False
    retries = -1
    errors = []

    while not segment_generated:
        retries += 1
        
        agent_query = f"""Write code to create the following visuals in Manim. Make the visuals as detailed as possible to fully illustrate the point.
    
{scene.visuals}. The animation should last for {duration_seconds} seconds."""

        if len(errors) > 0:
            agent_query += f"\n\nYou failed at this task when you attempted it previously. Here are the errors your past attempts have generated.: {errors}"

        manim_code = qa_chain.run(agent_query)

        try:
            parsed_code = fixing_parser.parse(manim_code)

#             ai_code = parsed_code.code.split("def construct(self):")[1].split('if __name__ == "__main__":')[0]

#             correct_code = f"""from manim import *

# class VideoVisual_{segment}(Scene):
#     def construct(self):
#         {ai_code}

# if frame == "main":
#     from manim import config

#     config.pixel_height = 1080
#     config.pixel_width = 1920

#     scene = VideoVisual_{segment}()
#     scene.render()"""

            with open(f"exec_test_{segment}.py", 'w') as pyfile:
                pyfile.write(parsed_code.code)

            os.system(f"python exec_test_{segment}.py")
        except Exception as e:
            errors.append(str(e))
            continue

        if os.path.isfile(f"media/videos/1080p60/VideoVisual_{segment}.mp4"):
            segment_generated = True
        else:
            retries += 1

        if retries > 10:
            raise Exception("Unable to generate video segment")

    # overlay audio onto video
    video = VideoFileClip(f"media/videos/1080p60/VideoVisual_{segment}.mp4")
    audio = AudioFileClip(filename)

    # Set the audio of the video to the provided audio
    final_video = video.set_audio(audio)
    
    # Write the result to a file
    final_video.write_videofile(f"final_{segment}.mp4", codec='libx264')

@app.route('/generatevideo', methods=['POST'])
def main():
    # handle CORS preflight
    # if request.method == 'OPTIONS':
    #     headers = {
    #         'Access-Control-Allow-Origin': '*',
    #         'Access-Control-Allow-Methods': 'GET',
    #         'Access-Control-Allow-Headers': 'Content-Type',
    #         'Access-Control-Max-Age': '3600'
    #     }

    #     return ('', 204, headers)

    # # set CORS return headers
    # cors_headers = {
    #     'Access-Control-Allow-Origin': '*'
    # }

    req_body = request.get_json()
    user_request = req_body['request']

    # user_request = request

    # generate storyboard
    template="You are an AI generating a video for a service called GPTeach. You do not have access to any visuals not generated by manim. Generate a concise storyboard that helps to explain the following concept/answer the provided question in the STYLE of a khan academy video. Use examples including latex, graphs, animations, charts, example problems, and more. Make it as visual as possible, and make sure there is always motion on screen. Follow the general format of intro-explanation of concept-example problem-summary, with additional explanation/example problem sections for more complex topics. A user should be able to watch the video and learn from it. You should answer in the following format: {formatting_instructions}"
    system_message_prompt = SystemMessagePromptTemplate.from_template(template)
    human_template="{text}"
    human_message_prompt = HumanMessagePromptTemplate.from_template(human_template)

    chat_prompt = ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])

    parser = PydanticOutputParser(pydantic_object=Storyboard)

    storyboard = parser.parse(chat(chat_prompt.format_prompt(formatting_instructions=parser.get_format_instructions(), text=user_request).to_messages()).content)
    segments, scenes = zip(*enumerate(storyboard.scenes))

    # delete old media
    if os.path.exists("media") and os.path.isdir("media"):
        shutil.rmtree("media")

    current_directory = os.getcwd()
    all_files = os.listdir(current_directory)
    files_to_delete = [file for file in all_files if file.startswith("VideoVisual_") or file.startswith("en-US-Studio-M")]
    for file in files_to_delete:
        try:
            os.remove(file)
            print(f"Deleted: {file}")
        except Exception as e:
            print(f"Error deleting {file}: {e}")

    # generate video segments
    # for segment, scene in zip(segments, scenes):
    #     generate_video_segment(segment, scene)
    with ThreadPoolExecutor(10) as executor:
        futures = executor.map(generate_video_segment, segments, scenes)
        wait(futures)

    # concatenate the video segments
    video_clips = []
    for segment in segments:
        try:
            video_clips.append(VideoFileClip(f"final_{segment}.mp4"))
        except:
            continue
    final_video = concatenate_videoclips(video_clips, method='compose')

    # output the video
    final_video.write_videofile("final.mp4", codec='libx264')

    # upload the video to cloud storage and return the download link
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(f"{uuid.uuid4()}.mp4")
    blob.upload_from_filename("final.mp4")
    video_url = blob.public_url

    return jsonify({"status": "success", "video_url": video_url}), 200

# # main("What is a vector field in calculus? Give a couple examples of different vector fields.")
# main("Visually explain t-tests in statistics.")

if __name__ == "__main__":
    app.run(debug=True)