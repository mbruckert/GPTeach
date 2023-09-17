import ast
from collections import OrderedDict
import re
import subprocess
from typing import Optional, Sequence, Type
import os
import shutil
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "shellhacks-2023-042c64c6e9eb.json"
import google.cloud.texttospeech as tts
from typing import List
from langchain.llms import OpenAI
from langchain.output_parsers import PydanticOutputParser, OutputFixingParser
from langchain.prompts import PromptTemplate
from langchain.pydantic_v1 import BaseModel, Field, validator
from langchain.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)
from typing import List
from langchain import PromptTemplate
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.tools import BaseTool
from flask import Flask, request, jsonify
from flask_cors import CORS
from langchain.chat_models import ChatOpenAI
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.chains import RetrievalQA
from langchain.schema import (
    SystemMessage,
)
from langchain.agents import initialize_agent, AgentType
from dotenv import load_dotenv
from enum import Enum
import json
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from pydub import AudioSegment
import uuid
import urllib.parse
from google.cloud import storage
import requests
import xmltodict

load_dotenv()
app = Flask(__name__)
CORS(app)
chat = ChatOpenAI(model="gpt-4")
vectorstore = Chroma(persist_directory="manim_vectorstore", embedding_function=OpenAIEmbeddings())
bucket_name = "shellhacks-2023"

class Answer(BaseModel):
    steps: list[str] = Field(description="The list of steps to solve the problem.")
    answer: str = Field(description="The answer to the problem.")

class WolframStepsRequest(BaseModel):
    question: str = Field(description="The question to be asked to Wolfram Alpha's step-by-step API. You should simplify the user's question as much as possible before passing it to this API e.g. plug in any values into equations, remove any words not absolutely necessary in the problem.")

class WolframStepsWrapper(BaseTool):
    name = "WolframStepsWrapper"
    description = "Makes a request to Wolfram Alpha's step-by-step api and returns the response."
    args_schema: Type[BaseModel] = WolframStepsRequest

    def _run(self, question: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> OrderedDict[str, any]:
        """Run a wolfram request synchronously"""
        safe_string = urllib.parse.quote_plus(question)
        resp = requests.get(f"http://api.wolframalpha.com/v2/query?appid=E9QV2Q-YAW469A5JK&input={safe_string}&podstate=Result__Step-by-step+solution&format=plaintext").text
        resp_dict = xmltodict.parse(resp)
        return resp_dict
    
    def _arun(self, question: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> OrderedDict[str, any]:
        """Run a wolfram request asynchronously"""
        raise NotImplementedError("Async not implemented for this tool.")

class SceneType(str, Enum):
    text = "text"
    example = "example"
    problem = "problem"

class Scene(BaseModel):
    info: str = Field(..., description="""Information you want to cover in this section. Be very specific about both what you want to convey and how you want to convey it
                      
Example of a good info field for a text scene:                                                                                                                                                                                                                         Reason:
'Introduce the idea of a limit by emphasizing its importance to calculus as a whole and then writing out the intuitive definition of a limit. Then write out the equation for the definition of a limit and explain how it matches the intuitive definition.'          The scene clearly and specifically conveys which conceptual/notational topics should be conveyed, how they conveyed, and with what equations. Also, it doesn't include any examples that would require calculations, or any visuals such as graphs

Examples of bad info fields for a text scene:                                                                                                                                                                                                                                                                                       Reasons:
'Introduce the idea of a limit.'                                                                                                                                                                                                                                                                                                    Not only does this not specifically state what information you want to convey, it doesn't say how it should be conveyed.
'Briefly introduce the idea of a limit. Then, write 1/(x^2) and ask the user where they think the function is undefined. Explain why the answer is 0, and then highlight the fact that despite the function being undefined at 0, the limit as x approaches 0 is infinite. Create a graph of the function to show this point.'      Instead of focusing on the concept at hand, this bad example jumps straight into an example which requires not only a graph, but also a calculation.
                      
Examples of good info fields for a problem scene:                                                                        Reasons:
'Solve the system of linear equations step by step, and graph its result, highlighting the intersection of the lines.'    This specifies the kind of problem to be solved and how the answer to that problem should be reinforced (in this case, with a graph)
'Solve the integral step by step, then show where someone could have gone wrong.'                                         This specifies the kind of problem to be solved and how the answer to that problem should be reinforced (in this case, by showing where someone could have gone wrong)    
                      
Examples of bad info fields for a problem scene:                                                        Reasons:
'Write out the problem and solve it'                                                                    This doesn't specify what kind of problem is being solved, and doesn't specify how the answer should be reinforced
'Graph the vector field of F(x,y) = [-y, x]. Explain what curl is and how this is an example of it'     This doesn't involve solving a problem at all; instead it displays a graphic example and explains a concept.
                      
Examples of good info fields for an example scene:                                                                                                                                                                                                                                                                                                                                                                      Reasons:
'Display a graph with two clusters of points, one of which is clearly linearly separable and one of which is not. Then, show on the graph how a linear classifier would classify the points, and explain why it would fail. Then, show on the graph how a non-linear classifier would classify the points, and explain why it would succeed.'                                                                           This clearly explains both how the example is being conveyed (in this case an animated graph) and what concept the example reinfoces/clarifies (in this case, the difference between linear and non-linear classifiers).
'Display the set of numbers [1,1,2,5,6,7,7,7,8,9,9,10,10,10,10,10] and then graphically transform that array into a histogram. Explain that histograms can be used to visualize data distributions.'                                                                                                                                                                                                                    This clearly explains both how the example is being conveyed (an animation of a set of numbers being transformed into a histogram) and what information is being conveyed (in this case, the idea that histograms can be used as a visual representation of numerical data) 
'Display a vector field with arrows circulating around the origin. Explain that this is an example of a vector field with curl'                                                                                                                                                                                                                                                                                         This clearly explains both how the example is being conveyed (an animation of a vector field) and what information is being conveyed (in this case, the idea that curl is a measure of how much a vector field circulates around a point)
'Demonstrate the concept of compound interest by considering a principal amount of $1000 with an annual interest rate of 5% compounded annually. Show that after the first year, the amount would be $1050. In the second year, interest is calculated on the new amount of $1050 and not the original principal. Explain how this can grow exponentially, and visualize this whole process with a labelled graph.'     This does not require a calculation, connects the example to a broader point, and explains how the example is being conveyed visually
                             
Examples of bad info fields for an example scene:                                                                                                                                                                                                                                                                       Reasons:
'Display the set of numbers [1,1,2,5,6,7,7,7,8,9,9,10,10,10,10,10] and then graphically transform that array into a histogram and display the mean. Then explain what a histogram is.'                                                                                                                                  This doesn't use visuals to reinforce or clarify a broader concept, it just gives information without attaching it to a broader concept.
'Give a graphical example of curl and explain how it demonstrates curl'                                                                                                                                                                                                                                                 This doesn't include a specific visual                     
'Demonstrate the concept of compound interest by considering a principal amount of $1000 with an annual interest rate of 5% compounded annually. Show that after the first year, the amount would be $1050. In the second year, interest is calculated on the new amount of $1050 and not the original principal.'      This doesn't include a visual. While it does connect it to the broader concept of compound interest, it doesn't really emphasize the importance of the subject.                                                                                                                                                  This doesn't specify what information is being conveyed, and doesn't specify how it should be conveyed.""") 
    sceneType: SceneType = Field(..., description="The type of scene you want to create. If you want to explain conceptual information about a topic or summarize previous points, use 'text'. Only text or LaTeX based visuals (e.g. equations) should be generated for this kind of scene. If you want to graphically demonstrate how something works, use 'example'. If you want to show a problem, use 'problem'.")
    problem: Optional[str] = Field(default=None,  description="""ONLY USE THIS FIELD IF YOU ARE CREATING A PROBLEM SCENE. This field is the practice problem you are solving in this scene, and it must be formatted so it can be fed directly to Wolfram Alpha to solve.
                                   
Example of a good problem:                      Reasons:
'Find the derivative of x^2 + 3x + 5'           This is a clear and specific problem with no extra information.
'row reduce [[1, 2, 3], [4, 5, 6], [7, 8, 9]]'  This is a clear and specific problem with no extra information.
'mean of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]'       This is a clear and specific problem with no extra information.
                                   
Example of bad problems:                                                                                                    Reasons:
'standard deviation and mean of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]'                                                            This asks for multiple things at once, and thus cannot be solved by Wolfram Alpha.
'Solve a problem using the chain rule'                                                                                      This fails to specify a problem, and thus cannot be solved by Wolfram Alpha.
'Write out the problem find the derivative of x^2 + 3x + 5 and then solve it, going step by step and explaining each step'  This is not a problem, this is a description of what you're going to present in the scene. The unnecessary information renders it unable to be solved by Wolfram Alpha.""")

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
    if scene.sceneType == SceneType.problem:
        Tools = [WolframStepsWrapper()]
        parser = PydanticOutputParser(pydantic_object=Answer)
        prefix = f"Use Wolfram Alpha to solve the given question and return the steps as well as the answer. You MUST respond with this output format: {parser.get_format_instructions()}"
        agent = initialize_agent(Tools, ChatOpenAI(model="gpt-4"), agent=AgentType.OPENAI_FUNCTIONS, verbose=True, agent_kwargs={
            "system_message": SystemMessage(content=prefix)
        })
        resp = agent.run("Calculate the compound interest for a principal amount of $5000 with an annual interest rate of 5% compounded annually for 3 years using the formula: A = P (1 + r/n)^(nt).")

    # get the audio for the segment
    # get the visuals for the segment

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
    retries = 0
    errors = []

    while not segment_generated:
        # break if too many retries
        if retries > 10:
            break

        # generate manim code
        agent_query = f"""Write code to create the following visuals in Manim. Make the visuals as detailed as possible to fully illustrate the point.
    
{scene.visuals}. The animation should last for {duration_seconds} seconds."""

        if len(errors) > 0:
            agent_query += f"\n\nYou failed at this task when you attempted it previously. Here are the errors your past attempts have generated.: {errors}"

        try:
            manim_code = qa_chain.run(agent_query)

            # process manim code and write it to file
            parsed_code = fixing_parser.parse(manim_code)

            with open(f"exec_test_{segment}.py", 'w') as pyfile:
                pyfile.write(parsed_code.code)

            # execute manim code
            os.system(f"python exec_test_{segment}.py")
            segment_generated = True
        except Exception as e:
            errors.append(str(e))
            retries += 1
            continue

    if os.path.isfile(f"media/videos/1080p60/VideoVisual_{segment}.mp4"):
        # # overlay audio onto video
        # video = VideoFileClip(f"media/videos/1080p60/VideoVisual_{segment}.mp4")
        # audio = AudioFileClip(filename)
        # # Set the audio of the video to the provided audio
        # final_video = video.set_audio(audio)
        
        # # Write the result to a file
        # final_video.write_videofile(f"final_{segment}.mp4", codec='libx264')
        subprocess.call(["ffmpeg", "-i", f"media/videos/1080p60/VideoVisual_{segment}.mp4", "-i", f"en-US-Studio-M_{segment}.wav", "-c:v", "copy", "-filter:a", "aresample=async=1", "-c:a", "flac", "-strict", "-2", f"final_{segment}.mp4"])

@app.route('/generatevideo', methods=['POST'])
def main():
    req_body = request.get_json()
    user_request = req_body['request']

    # user_request = request

    # generate storyboard
    template="""You are an AI generating a video for a service called GPTeach. You do not have access to any visuals not generated by manim. Generate a concise storyboard that helps to explain the following concept/answer the provided question in the STYLE of a khan academy video. 
    
You can use text scenes, example scenes, and problem scenes. Text scenes should be used to introduce and explain conceptual information about a topic or summarize previous points. Visuals in text scenes can be text or LaTeX equaitons. Example scenes should be used to graphically provide reinforcment of clarification for a broader point. Example scenes MUST have a clearly defined visual component that highlights the point. They MUST not include a calculation. Problem scenes should be used to show how a concept can be applied in solving a problem. Problems MUST be accompanied by a problem. Visuals in problem scenes are not necessary but ar often and, if present, should serve to complement the problem being solved, and should be used to reinforce the solution to the problem.

Your storyboard must have a logical flow. It is highly recommended that you start with a text scene to introduct the topic, fill the middle of the video with text-example-problem pairings developing the finer points of the video's topic, and end with a text scene summarizing everything you covered in the video and tying the lesson together. However, you can deviate from this format if you believe it will aid the learning experience. For example if you are covering a more complex or nuanced topic multiple examples may be necessary to fully convey the topic, or for a more challenging topic more examples may be required to give students a good idea of how the concept can be applied.
    
You should answer in the following format: {formatting_instructions}"""
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
    files_to_delete = [file for file in all_files if file.startswith("final") or file.startswith("en-US-Studio-M") or file.startswith("exec_test_")]
    for file in files_to_delete:
        try:
            os.remove(file)
            print(f"Deleted: {file}")
        except Exception as e:
            print(f"Error deleting {file}: {e}")

    # generate video segments
    # for segment, scene in zip(segments, scenes):
    #     generate_video_segment(segment, scene)
    with ThreadPoolExecutor(5) as executor:
        executor.map(generate_video_segment, segments, scenes)

    print(os.listdir())

    # concatenate the video segments
    video_clips_str = ""
    for segment in segments:
        if os.path.isfile(f"final_{segment}.mp4"):
            video_clips_str += f"file 'final_{segment}.mp4'\n"
    with open("video_clips.txt", "w") as f:
        f.write(video_clips_str)
    subprocess.call(["ffmpeg", "-f", "concat", "-safe", "0", "-i", "video_clips.txt", "-c", "copy", "-strict", "-2", "final.mp4"])

    # video_clips = []
    # for segment in segments:
    #     try:
    #         video_clips.append(VideoFileClip(f"final_{segment}.mp4"))
    #     except:
    #         continue
    # final_video = concatenate_videoclips(video_clips, method='compose')
    # # output the video
    # final_video.write_videofile("final.mp4", codec='h264')

    # upload the video to cloud storage and return the download link
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(f"{uuid.uuid4()}.mp4")
    blob.upload_from_filename("final.mp4")
    blob.make_public()
    video_url = blob.public_url
    print(video_url)

    return jsonify({"status": "success", "video_url": video_url}), 200

# main("What is a vector field in calculus? Give a couple examples of different vector fields.")
# main("Explain long division")

if __name__ == "__main__":
    app.run(debug=True)