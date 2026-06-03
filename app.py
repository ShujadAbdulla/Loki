
import gradio as gr
import requests
import os
from langchain_groq import ChatGroq
from langchain_tavily import TavilySearch



groq_key = os.getenv("groq")
tavily_api = os.getenv("tavily_API")
rapid_api = os.getenv("J_search")

from langchain_groq import ChatGroq

model = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=groq_key,
    temperature=0.3
)

tavily = TavilySearch(
    max_results=5,
    tavily_api_key=tavily_api
)
def extract_skill(query):

    prompt = f"""
    Extract the main career skill from this query.

    Query: {query}

    Return only the skill name.
    """

    response = model.invoke(prompt)

    return response.content.strip()

def get_skill_demand(skill):

    results = tavily.invoke({
        "query": f"{skill} demand in industry 2026 salary trends"
    })

    return str(results)  

def get_jobs(skill):

    url = "https://jsearch.p.rapidapi.com/search"

    headers = {
        "x-rapidapi-key": rapid_api,
        "x-rapidapi-host": "jsearch.p.rapidapi.com"
    }

    params = {
        "query": f"{skill} jobs in India",
        "page": "1"
    }

    response = requests.get(url, headers=headers, params=params)

    data = response.json()

    return data.get("data", [])[:5]  
def generate_answer(skill, demand, jobs):

    job_text = ""

    for job in jobs:

        title = job.get("job_title")
        company = job.get("employer_name")
        location = job.get("job_city")
        link = job.get("job_apply_link")

        job_text += f"""
### {title}
Company: {company}  
Location: {location}  
Apply: [{link}]({link})

"""

    prompt = f"""
Skill: {skill}

Industry demand:
{demand}

Job listings with apply links:
{job_text}

Explain:

1. Future demand
2. Salary estimate
3. Learning roadmap

Then show the job opportunities EXACTLY with the apply links.

Important:
Do not remove or modify the apply links.
Display them clearly so the user can click them.
"""

    response = model.invoke(prompt)

    return response.content
def generate_roadmap(skill):

    prompt = f"""
    Create a learning roadmap for becoming a {skill}.

    Include:
    - beginner skills
    - intermediate skills
    - advanced skills
    - tools to learn
    """

    response = model.invoke(prompt)

    return response.content

def generate_response(skill, demand, jobs, salary, roadmap):

    job_text = ""

    for job in jobs:

        job_text += f"""
Title: {job.get('job_title')}
Company: {job.get('employer_name')}
Location: {job.get('job_city')}
Apply: {job.get('job_apply_link')}

"""

    prompt = f"""
Skill: {skill}

Industry Demand:
{demand}

Salary Insights:
{salary}

Jobs:
{job_text}

Learning Roadmap:
{roadmap}

Create a clean formatted response.
"""

    response = model.invoke(prompt)

    return response.content
def career_copilot(query):

    skill = extract_skill(query)

    demand = get_skill_demand(skill)

    jobs = get_jobs(skill)

    answer = generate_answer(skill, demand, jobs)

    return answer
def chat(message, history):

    try:
        return career_copilot(message)

    except Exception as e:
        return str(e)


demo = gr.ChatInterface(
    fn=chat,
    title="🚀 AI Career Copilot",
    description="Discover job demand, salary insights and learning roadmap"
)

demo.launch()
