# Importing the neccesary libraries
import pandas as pd
import numpy as np
import streamlit as st
import langchain
from langchain_groq import ChatGroq
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.chains import RetrievalQAWithSourcesChain
from langchain.vectorstores import FAISS
from sentence_transformers import SentenceTransformer
from sklearn.neighbors import NearestNeighbors
from streamlit_feedback import streamlit_feedback
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from datetime import datetime
import time
import os
from dotenv import load_dotenv

# Setup Configs #
AVATARS = {
    "user": "👤",
    "ai": "🤖"
}

HIDEMENU = """
<style>
.stApp [data-testid="stHeader"] { 
    display:none; 
}
p img { 
    margin-bottom: 0.6rem; 
}
[data-testid="stSidebarCollapseButton"], [data-testid="baseButton-headerNoPadding"] { 
    display:none; 
}
.stChatInput button { 
    display:none; 
}

/* Set background and text */
body, .stApp {
    background-color: white !important;
    color: black !important;
}

img{
    border: 1px solid black;
}

p{
    color: black;
}

/* Header text */
h1, h2, h3, h4, h5, h6 {
    color: black !important;
}

/* Buttons and secondary elements */
button, .stButton>button {
    background-color: #4A8FD6 !important;
    color: white !important;
    border: none;
    border-radius: 8px;
    padding: 0.5rem 1rem;
}

button:hover {
    background-color: #286FB4 !important;
}

/* Chat messages */
.stChatMessage {
    background-color: #f5f5f5 !important;
    border-radius: 10px;
    padding: 10px;
    color: black ;
    margin-bottom: 1rem;
}

div[data-baseweb="input"] > div {
    background-color: #f9f9f9 !important;
    border-radius: 10px;
}

input {
    background-color: #f9f9f9 !important;
    color: black !important;
}

.st-emotion-cache-4oy321 { 
    background-color: white !important;
}

.st-emotion-cache-janbn0 {
    background-color: white !important;
}

.st-emotion-cache-18qnold{
    background-color: #4A8FD6 !important;
    border-radius: 100px;
}

:root {
    --background-color: #FFFFFF;
}

.st-emotion-cache-hzygls {
    background-color: white !important;
}

.st-be {
    background-color: white !important;
    color: #555555 !important;  
}

.st-be::placeholder{
    color: #444444 !important;
}

.st-emotion-cache-x1bvup {
    background-color: white !important;
    border: 2px solid black !important;
}

.st-bs {
    caret-color: black !important;
}

.st-emotion-cache-hkjmcg {
    background-color: white !important;
    border: 2px solid black !important;
}

.st-c4 {
    caret-color: black !important;
}

li{
    color: black !important;
}

</style>

"""

## LibrarAI

st.set_page_config(page_title="GyanAI", page_icon="🤖", initial_sidebar_state="collapsed")
st.markdown(HIDEMENU, unsafe_allow_html=True)

# Load Vector Store #
@st.cache_resource(ttl="1d", show_spinner=False)
def load_faiss_index():
    embeddings = HuggingFaceEmbeddings(
        model_name="thenlper/gte-base",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )
    # Loading the vector embeddings from .pkl file
    file_path="faiss_index"
    vectorIndex = FAISS.load_local(file_path, embeddings, allow_dangerous_deserialization=True)
    
    model = SentenceTransformer("all-MiniLM-L12-v2")
    try:
        faq_data = pd.read_csv("FAQs.csv", encoding="utf-8-sig")
    except:
        faq_data = pd.DataFrame(columns=['Questions','Answers'])
    return vectorIndex,model,faq_data

# Creating Bot #
@st.cache_resource(show_spinner=False)
def create_bot():
    faiss_index,model,faq_data = load_faiss_index()
    # Setting up on what basis it will search for answer.
    retriever = faiss_index.as_retriever(search_type="similarity", search_kwargs={"k": 3})
    
    # Setting the LLM
    load_dotenv()
    llm = ChatGroq(
        groq_api_key = os.getenv("GROQ_API_KEY"),
        model_name="llama3-70b-8192"
    )
    
    # Initializing the Question and Answer Chain
    qa_chain = RetrievalQAWithSourcesChain.from_llm(
        llm=llm,
        retriever=retriever,
        return_source_documents=True
    )
    
    questions = faq_data["Questions"].tolist()
    embeddings = model.encode(questions)
    nn = NearestNeighbors(n_neighbors=4, metric='cosine').fit(embeddings)
    
    return qa_chain, nn, model, faq_data

def show_related_question_buttons(user_query, nn, model, faq_data):
    query_embedding = model.encode([user_query])
    questions = faq_data["Questions"].tolist()
    _, indices = nn.kneighbors(query_embedding)
    suggestions = [questions[i] for i in indices[0]]
    st.markdown("#### Related Questions:")
    if (suggestions[0]==user_query):
        if (len(suggestions)>3):
            col1, col2, col3 = st.columns(3)
            if col1.button(suggestions[1]):
                st.session_state.clicked_suggestion = suggestions[1]
                st.rerun()
                
            if col2.button(suggestions[2]):
                st.session_state.clicked_suggestion = suggestions[2]
                st.rerun()

            if col3.button(suggestions[3]):
                st.session_state.clicked_suggestion = suggestions[3]
                st.rerun()

    else:
        if (len(suggestions)>2):
            col1, col2, col3 = st.columns(3)
            if col1.button(suggestions[0]):
                st.session_state.clicked_suggestion = suggestions[0]
                st.rerun()
                
            if col2.button(suggestions[1]):
                st.session_state.clicked_suggestion = suggestions[1]
                st.rerun()

            if col3.button(suggestions[2]):
                st.session_state.clicked_suggestion = suggestions[2]
                st.rerun()

# Query Bot #
def query_bot(query, bot):
    start_time = time.time()
    processed_query = query.replace(" issue "," borrow ")
    processed_query_2 = processed_query.replace(" fine "," fee ")
    
    # Storing the answers and sources 
    answer = ""
    sources = ""
    # Some pre-defined answers from the Chatbot
    if (query.lower() == "hi" or query.lower() == "hello" or query.lower() == "hey"):
        answer = "Hello! How can I assist you today?"
        sources = ""
    elif (query == "Where is the library?"):
        answer = "The Main Library is located in Block 13, and there is a Mini Library, an extension of the Library, located in Emiet Hostel.\n\n"
        sources = "https://library.iitgn.ac.in/faqs.php"
    elif (query == "How can I borrow books using an RFID kiosk?"):
        answer = "You can borrow books using an RFID kiosk by clicking on 'Issue' on the screen, tapping your Institute ID card/ Library Card against the card reader, typing your account password, placing the books on the scan bed, clicking on 'Done', and collecting the receipt."
        sources = "https://library.iitgn.ac.in/faqs.php"
    elif (query == "How do I search our library catalog?"):
        answer = "You can search the library catalog at https://catalog.iitgn.ac.in/ by the full or partial title, author name, Subject, ISBN, series, and Call number."
        sources = "https://library.iitgn.ac.in/faqs.php"
    else:
        # Getting the response from the LLM.
        try:
            langchain.debug = True
            for _ in range(2):        
                response = bot({"question": processed_query_2}, return_only_outputs=False)
                answer = response.get("answer", "").strip()
                sources = response.get("sources", "").strip()
                if answer and "don't know" not in answer.lower():
                    break
            else:
                # The answer is not in the bot's knowledge
                answer = "Sorry, we can't get the answer of the question. \n\n-Please again ask the same question more precisely. \n\n-Contact us on Email - librarian@iitgn.ac.in or Phone Number - +91-079-2395-2431"
                sources = "https://library.iitgn.ac.in/"
        except:
            answer = "Thanks for connecting! All the agents are currently busy. Please try again after 1 minute.\n\nWhile you wait, feel free to browse our Library Website - https://library.iitgn.ac.in/ or Search the Catalogue - https://catalog.iitgn.ac.in/."
            sources = ""
        answer = answer.removeprefix("FINAL ANSWER: ").strip()
    
    # Storing the user and ai answer
    bot_answer = answer+"\n\nSources: "+sources
    st.session_state.chat_history.append(("user", query))
    st.session_state.chat_history.append(("ai", bot_answer))
    end_time = time.time()
    total_time = end_time - start_time
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    try:
        try:
            df = pd.read_csv('data.csv')
        except:
            df = pd.DataFrame(columns=['Date', 'Time', 'User Question', 'Chatbot Answer', 'Time Taken(in sec)'])
        new_entry = {'Date':date_str,'Time':time_str,'User Question':query,'Chatbot Answer':answer,'Time Taken(in sec)':total_time}
        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
        df.to_csv('data.csv', index=False)
    except:
        pass
    return answer, sources
    
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
    st.session_state.chat_history.append(("ai", "How can I help you today?"))
    
# Load the bot
if "chatbot" not in st.session_state:
    st.session_state.chatbot, st.session_state.nn, st.session_state.model, st.session_state.faq_data  = create_bot()
    st.session_state.feedback_done = False 

# Main App #
with st.container():
    # Bot Title
    col1, col2 = st.columns([1, 5])  # Adjust column widths as needed

    with col1:
        st.image("lib.png", width=120)

    with col2:
        st.markdown("<h1 style='margin-bottom: 0; padding-bottom: 0;'>Hi, I'm GyanAI</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='margin-top: 0; padding-top: 0;'>Your Library Assistant</h3>", unsafe_allow_html=True)

    # Buttons
    col1, col2, col3, col4 = st.columns(4)
    if col1.button("Library Hours"):
        today = datetime.now()
        day_name = today.strftime('%A')
        query = f"What are the Library hours on {day_name}?"
        query_bot(query, st.session_state.chatbot)
        st.session_state.last_question = query

    if col2.button("Library Location"):
        query = "Where is the library?"
        query_bot(query, st.session_state.chatbot)
        st.session_state.last_question = query
            
    if col3.button("Borrow Books"):
        query = "How can I borrow books using an RFID kiosk?"
        query_bot(query, st.session_state.chatbot)
        st.session_state.last_question = query
        
    if col4.button("Finding Book"):
        query = "How do I search our library catalog?"
        query_bot(query, st.session_state.chatbot)
        st.session_state.last_question = query

# Render past messages
for role, msg in st.session_state.chat_history:
    st.chat_message(role, avatar=AVATARS[role]).write(msg)

# Input
if user_query := st.chat_input("Ask me about the Library!"):
    st.chat_message("user", avatar=AVATARS["user"]).write(user_query)
    with st.chat_message("ai", avatar=AVATARS["ai"]):
        with st.spinner("Thinking..."):
            answer, sources = query_bot(user_query, st.session_state.chatbot)
            st.write(answer)
            st.write("Sources:", sources)
    st.session_state.last_question = user_query

if "clicked_suggestion" in st.session_state:
    query = st.session_state.pop("clicked_suggestion")
    st.chat_message("user", avatar=AVATARS["user"]).write(query)
    with st.chat_message("ai", avatar=AVATARS["ai"]):
        with st.spinner("Thinking..."):
            answer, sources = query_bot(query, st.session_state.chatbot)
            st.write(answer)
            st.write("Sources:", sources)
    st.session_state.last_question = query

if "last_question" in st.session_state:
    show_related_question_buttons(st.session_state.last_question, st.session_state.nn, st.session_state.model, st.session_state.faq_data)
    
# Feedback
streamlit_feedback(
    feedback_type="thumbs",
    optional_text_label="Optional. Please provide extra information",
    key="feedback",
    args=("feedback",)
)

if "feedback" in st.session_state and st.session_state["feedback"] is not None:
    try:
        try:
            df = pd.read_csv('feedback.csv')
        except:
            df = pd.DataFrame(columns=['Date','Time','Feedback','Feedback Text'])
        try:
            prev_comment = df.values[-1][-1]
        except:
            prev_comment = "qazwsxedc"
        if (st.session_state["feedback"]["text"]!=None):
            feedback_text = st.session_state["feedback"]["text"]
        else:
            feedback_text = ""
        if (feedback_text != prev_comment): 
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            feedback = st.session_state["feedback"]["score"]
            if (feedback == "👍"):
                feedback = "Good"
            else:
                feedback = "Bad"
            
            new_entry = {'Date':date_str,'Time':time_str,'Feedback':feedback,'Feedback Text':feedback_text}
            df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
            df.to_csv('feedback.csv', index=False)     
        else:
            pass
    except:
        pass

# Chat Action Buttons
st.markdown("<br>", unsafe_allow_html=True)
col_btn1, col_btn2, col_btn3= st.columns([1, 1, 1])

with col_btn1:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=30, leftMargin=30,
                            topMargin=30, bottomMargin=18)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ChatStyle', fontSize=12, leading=15))
    
    flowables = []

    for role, msg in st.session_state.chat_history:
        formatted = f"<b>{role.capitalize()}:</b> {msg}"
        para = Paragraph(formatted, styles["ChatStyle"])
        flowables.append(para)
        flowables.append(Spacer(1, 12))

    doc.build(flowables)

    buffer.seek(0)
    filename = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    st.download_button("💾 Save Chat", data=buffer, file_name=filename, mime="application/pdf", key="download_pdf_btn")

with col_btn2:
    if st.button("☎️ Talk to a libraian"):
        query = "Talk to a librarian"
        answer = "You can chat with a librarian here: http://localhost:3000/"
        st.session_state.chat_history.append(("user", query))
        st.session_state.chat_history.append(("ai", answer))
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        try:
            df = pd.read_csv('data.csv')
        except:
            df = pd.DataFrame(columns=['Date', 'Time', 'User Question', 'Chatbot Answer', 'Time Taken(in sec)'])
        new_entry = {'Date':date_str,'Time':time_str,'User Question':query,'Chatbot Answer':answer,'Time Taken(in sec)':0.00}
        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
        df.to_csv('data.csv', index=False)
        st.rerun()

with col_btn3:
    if st.button("🗑️ Clear Chat"):
        st.session_state.chat_history = [("ai", "Hi! How can I help you today?")]
        try:
            del(st.session_state.last_question)
            st.rerun()
        except:
            st.rerun()
        
# Disclaimer
st.markdown(
    """
    <div style='text-align: center; font-size: 0.9em; color: gray; margin-top: 2em;'>
        ⚠️ Disclaimer: GyanAI may generate incorrect or outdated information. Please verify from sources given. Keep your questions short and general for best results.
    </div>
    """,
    unsafe_allow_html=True
)
# st.write("DEBUG session_state:", dict(st.session_state))