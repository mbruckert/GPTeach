import logo from './logo.svg';
import React, {useState} from 'react';
import './App.css';
import {Textarea, Spinner, Button} from '@primer/react'
import { SyncIcon } from "@primer/octicons-react";
import {ThemeProvider} from '@primer/react';
import { Player, BigPlayButton } from 'video-react';
import 'video-react/dist/video-react.css';
import { OpenAI } from "langchain/llms/openai";
import { PromptTemplate } from "langchain/prompts";
import { StructuredOutputParser } from "langchain/output_parsers";
import useWindowSize from 'react-use/lib/useWindowSize'
import Confetti from 'react-confetti'
import toast, { Toaster } from 'react-hot-toast';

function App() {

  const [topic, setTopic] = useState("");
  const [question, setQuestion] = useState("");
  const [answerChoices, setAnswerChoices] = useState([]);
  const [selectedOption, setSelectedOption] = useState("");
  const [correctAnswer, setCorrectAnswer] = useState("");
  const [validatedAnswer, setValidatedAnswer] = useState({});
  const [showConfetti, setShowConfetti] = useState(false);
  const [loadedVideo, setLoadedVideo] = useState(false);
  const [loadedAnswer, setLoadedAnswer] = useState(false);
  const [videoUrl, setVideoUrl] = useState("");

  const { width, height } = useWindowSize()

  async function getQuestionAnswers(inputTopic){

    const parser = StructuredOutputParser.fromNamesAndDescriptions({
      question: "a question about the given topic to test the user's knowledge.",
      answerChoices: "should be an array of strings which contain answer choices for the question.",
    });
    
    const formatInstructions = parser.getFormatInstructions();
  
    const prompt = new PromptTemplate({
      template:
        "Generates a question (if about math, give a calculation to solve) to test the user's knowledge of the given topic and also generates 4 potential answer choices. OUTPUT JSON THAT I COULD DIRECTLY COPY AND PASTE INTO A VALIDATOR, WITH NO OTHER TEXT INCLUDING MARKDOWN. YOUR OUTPUT MUST START WITH A BRACKET AND END WITH A BRACKET.\n{format_instructions}\n The given topic is: {topic} \n\n ",
      inputVariables: ["topic"],
      partialVariables: { format_instructions: formatInstructions },
    });
  
    const model = new OpenAI({ temperature: 0, openAIApiKey: process.env.REACT_APP_OPENAI_API_KEY });
  
    const input = await prompt.format({
      topic: inputTopic,
    });
    
    const response = await model.call(input);

    console.log(response);

    const output = JSON.parse(response);
    setQuestion(output.question);
    setAnswerChoices(output.answerChoices);
    }

    async function checkAnswer(question, answerChoices, selectedOption) {
      return new Promise(async (resolve, reject) => {
        try {
          const response = await fetch('https://corsproxy.io/?' + encodeURIComponent("https://www.wolframalpha.com/api/v1/llm-api?input=" + encodeURIComponent(question) + "&appid=EKVAQ3-853KWTJT6P"));
          const data = await response.text();
    
          setCorrectAnswer(data);
    
          const booleanParser = StructuredOutputParser.fromNamesAndDescriptions({
            correct: "a true or false boolean stating whether the given answer for the question is correct.",
            correctAnswer: "the correct answer for the given question.",
            explanation: "why the given answer is correct, over the selected answer.",
          });
    
          const correctFormatInstructions = booleanParser.getFormatInstructions();
    
          const correctPrompt = new PromptTemplate({
            template:
              "You are given the question: {question} and the answer choices: {answerChoices}. You are asked to select the correct answer choice. Information that might provide the correct answer is provided here (only use this information if the problem involves a calculation, conversion, or something similar - otherwise use your own knowledge): {correctAnswer}. OUTPUT JSON THAT I COULD DIRECTLY COPY AND PASTE INTO A VALIDATOR, WITH NO OTHER TEXT INCLUDING MARKDOWN. YOUR OUTPUT MUST START WITH A BRACKET AND END WITH A BRACKET.\n{format_instructions}\n Is the given answer choice correct (it needs to be exactly correct, not close)? {answerChoice} \n\n ",
            inputVariables: ["question", "answerChoices", "correctAnswer", "answerChoice"],
            partialVariables: { format_instructions: correctFormatInstructions },
          });
    
          const input = await correctPrompt.format({
            question: question,
            answerChoices: answerChoices,
            correctAnswer: data,
            answerChoice: selectedOption
          });
    
          console.log(input);
    
          const model = new OpenAI({ temperature: 0, openAIApiKey: process.env.REACT_APP_OPENAI_API_KEY });
          const openAIResponse = await model.call(input);
          const output = JSON.parse(openAIResponse);
    
          if (output.correct === "true") {
            setShowConfetti(true);
            setTimeout(() => {
              setShowConfetti(false);
            }, 5000);
          }
    
          setValidatedAnswer(output);
          resolve(output);
        } catch (error) {
          reject(error);
        }
      });
    }

  async function generateVideo(){
    toast.success('Generating your video! This may take a few minutes.');
    fetch("https://generatevideo-ahaig2rvna-uc.a.run.app/generatevideo", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({"request": topic})
    }).then((response) => response.json()).then((data) => {
      setLoadedVideo(true);
      setVideoUrl(data.video_url);
      toast.success('Your video has been generated!');
    });
  }

  return (
    <ThemeProvider>
      <div><Toaster/></div>
    <div className="App" style={{backgroundImage:`url(${process.env.PUBLIC_URL+ "/background.png"})`, width: '100%', height: '135vh', backgroundSize: 'cover'}}>
      <div style={{position: 'absolute', width: '100%'}}>
          <div style={{width: '100%', height: '70px', backgroundColor: 'white', display: 'flex', gap: '10px', alignItems: 'center', borderBottom: '1px solid #BDBDBD', paddingLeft: '20px', position: 'fixed'}}>
          <div style={{display: 'flex', justifyContent: 'space-between', width: '97%', alignItems: 'center'}}>
            <div style={{display: 'flex', gap: '20px'}}>
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6" style={{width: '30px'}}>
                <path d="M11.7 2.805a.75.75 0 01.6 0A60.65 60.65 0 0122.83 8.72a.75.75 0 01-.231 1.337 49.949 49.949 0 00-9.902 3.912l-.003.002-.34.18a.75.75 0 01-.707 0A50.009 50.009 0 007.5 12.174v-.224c0-.131.067-.248.172-.311a54.614 54.614 0 014.653-2.52.75.75 0 00-.65-1.352 56.129 56.129 0 00-4.78 2.589 1.858 1.858 0 00-.859 1.228 49.803 49.803 0 00-4.634-1.527.75.75 0 01-.231-1.337A60.653 60.653 0 0111.7 2.805z" />
                <path d="M13.06 15.473a48.45 48.45 0 017.666-3.282c.134 1.414.22 2.843.255 4.285a.75.75 0 01-.46.71 47.878 47.878 0 00-8.105 4.342.75.75 0 01-.832 0 47.877 47.877 0 00-8.104-4.342.75.75 0 01-.461-.71c.035-1.442.121-2.87.255-4.286A48.4 48.4 0 016 13.18v1.27a1.5 1.5 0 00-.14 2.508c-.09.38-.222.753-.397 1.11.452.213.901.434 1.346.661a6.729 6.729 0 00.551-1.608 1.5 1.5 0 00.14-2.67v-.645a48.549 48.549 0 013.44 1.668 2.25 2.25 0 002.12 0z" />
                <path d="M4.462 19.462c.42-.419.753-.89 1-1.394.453.213.902.434 1.347.661a6.743 6.743 0 01-1.286 1.794.75.75 0 11-1.06-1.06z" />
              </svg>
              <h1 style={{color: 'black', fontSize: '25px', fontWeight: '700'}}>GP<span style={{color: '#127C01'}}>Teach</span></h1>
              </div>
              <Button leadingIcon={SyncIcon} onClick={() => {
                //reset all states
                setTopic("");
                setQuestion("");
                setAnswerChoices([]);
                setSelectedOption("");
                setCorrectAnswer("");
                setValidatedAnswer({});
                setLoadedVideo(false);
                setLoadedAnswer(false);
                setShowConfetti(false);
                toast.success('Session has been reset!');
              }}>Reset Session</Button>
          </div>
        </div>
        <div style={{display: 'flex'}}>
          <div style={{width: '60%', padding: '20px', marginTop: '70px', display: 'flex', flexDirection: 'column', justifyContent: 'start', alignItems: 'start'}}>
            <h1 style={{textAlign: 'left', fontSize: '25px'}}>📚 What do you need help with?</h1>
            <div style={{display: 'flex', alignItems: 'center', gap: '10px', marginTop: '-30px'}}>
              <div style={{backgroundColor: '#127C01', width: '15px', height: '15px', borderRadius: '20px'}}></div>
              <h6 style={{fontWeight: '900', fontSize: '17px', color: '#127C01'}}>YOU</h6>
            </div>
            <div style={{marginTop: '-30px', display: 'flex', flexDirection: 'column'}}>
              <Textarea value={topic} onChange={(e) => {
                setTopic(e.target.value);
              }} placeholder="Enter a topic or question" style={{width: '500px'}} />
              <div style={{display: 'flex', gap: '10px'}}>
                <p style={{fontWeight: '700'}}>OR choose one of these examples:</p>
                <p onClick={() => {
                  setTopic("Visually explain t-tests in statistics.");
                }} style={{textDecoration: 'underline', cursor: 'pointer'}}>Explain t-tests (Statistics)</p>
                <p onClick={() => {
                  setTopic("Teach me about derivatives.");
                }} style={{textDecoration: 'underline', cursor: 'pointer'}}>Explain derivatives (Calculus)</p>
              </div>
              <button onMouseOver={e => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.63)'} onMouseOut={e => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.43)'} onClick={() => {
                generateVideo();
                getQuestionAnswers(topic);
                if(topic == ""){
                  toast.error('You must include a topic or question to get help with!');
                } else{
                  getQuestionAnswers(topic);
                }
              }} style={{
                borderRadius: "10px", 
                border: "1px solid #127C01", 
                background: "rgba(255, 255, 255, 0.43)", 
                fontWeight: '700', 
                color: '#127C01', 
                height: '40px', 
                fontSize: '18px', 
                marginTop: '15px',
                cursor: 'pointer'
              }}>Get Help Now</button>
              {!loadedVideo && question !== "" && <div style={{display: 'flex', justifyContent: 'center'}}><Spinner style={{marginTop: '120px'}}/></div>}
              {loadedVideo && (
              <div style={{marginTop: '20px'}}>
                <div style={{display: 'flex', alignItems: 'center', gap: '10px', marginTop: '-30px'}}>
                <div style={{backgroundColor: 'black', width: '15px', height: '15px', borderRadius: '20px'}}></div>
                  <h6 style={{fontWeight: '900', fontSize: '17px', color: 'black'}}>GPTEACHER</h6>
                </div>
                <div style={{marginTop: '-20px'}}>
                  <Player>
                    <BigPlayButton position="center" />
                    <source src={videoUrl} />
                  </Player>
                </div>
              </div>
              )}
            </div>
          </div>
          <div style={{marginTop: '90px'}}>
          {question && loadedVideo && <div style={{marginTop: '20px', display: 'flex', flexDirection: 'column', alignItems: 'start'}}>
            <h1 style={{textAlign: 'left', fontSize: '25px'}}>🚀 {question}</h1>
            <div style={{display: 'flex', flexDirection: 'column', alignItems: 'start', gap: '0px', width: '40%'}}>
              {answerChoices.map((answerChoice) => {
                return <div style={{display: 'flex', gap: '2px', width: '200%'}}><input
                type="radio"
                value={answerChoice}
                checked={selectedOption === answerChoice}
                onChange={() => {
                  setSelectedOption(answerChoice);
                }}
              />
              <p style={{textAlign: 'left'}}>{answerChoice}</p>
              </div>
              }
              )}
              <button onClick={() => {
                if(selectedOption == ""){
                  toast.error('You must select an answer choice!');
                } else{
                  toast.promise(checkAnswer(question, answerChoices, selectedOption), {loading: "Checking your answer with Wolfram Alpha, please wait a moment...", success: "Your answer has been checked!", error: "There was an error checking your answer, please try again."});
                  checkAnswer(question, answerChoices, selectedOption);
                }
              }} onMouseOver={e => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.63)'} onMouseOut={e => e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.43)'} style={{borderRadius: "10px", border: "1px solid #127C01", background: "rgba(255, 255, 255, 0.43)", fontWeight: '700', color: '#127C01', height: '40px', fontSize: '18px', marginTop: '15px', width: '150%', cursor: 'pointer'}}>Check my Answer</button>

              {Object.keys(validatedAnswer).length > 0 && <div style={{marginTop: '20px', textAlign: 'left'}}>
                <div style={{backgroundColor: 'white', padding: '5px', width: '180%', borderRadius: '10px', textAlign: 'center'}}><h3>Your Answer is... {validatedAnswer.correct == "true" ? <span style={{color: '#127C01'}}>Correct!</span> : <span style={{color: '#C11111'}}>Incorrect :(</span>}</h3></div>
                {validatedAnswer.correct == "false" && <h4 style={{width: '150%'}}>Correct Answer: {validatedAnswer.correctAnswer}</h4>}
                {validatedAnswer.correct == "false" && <h4 style={{width: '150%'}}>Explanation: {validatedAnswer.explanation}</h4>}
                <h4 style={{width: '200%'}}>Answer Verified by Wolfram Alpha</h4>
              </div>}
            </div>
          </div>
          }
          </div>
        </div>
        </div>
    </div>
    {showConfetti &&
    <Confetti
      width={width}
      height={height}
      run={showConfetti}
    />
    }
    </ThemeProvider>
  );
}

export default App;
