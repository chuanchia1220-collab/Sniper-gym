import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import logging
import datetime

# Internal Modules
from game_logic import load_exam_data, filter_questions, calculate_result, generate_mock_data
from logger import log_error

# Set Page Config
st.set_page_config(layout="wide", page_title="Sniper Gym")

# --- Initialize Session State ---
if 'current_question_index' not in st.session_state:
    st.session_state.current_question_index = 0
if 'score' not in st.session_state:
    st.session_state.score = {'wins': 0, 'losses': 0, 'pnl': 0.0}
if 'game_mode' not in st.session_state:
    st.session_state.game_mode = 'Easy'
if 'user_answered' not in st.session_state:
    st.session_state.user_answered = False
if 'current_question_data' not in st.session_state:
    st.session_state.current_question_data = None
if 'stock_df' not in st.session_state:
    st.session_state.stock_df = None
if 'index_df' not in st.session_state:
    st.session_state.index_df = None


# --- Sidebar ---
st.sidebar.title("Sniper Gym 🎯")
game_mode = st.sidebar.selectbox("Select Difficulty", ["Easy", "Medium", "Hard", "Realistic"], index=["Easy", "Medium", "Hard", "Realistic"].index(st.session_state.game_mode))

if game_mode != st.session_state.game_mode:
    st.session_state.game_mode = game_mode
    st.session_state.current_question_index = 0
    st.session_state.score = {'wins': 0, 'losses': 0, 'pnl': 0.0}
    st.session_state.user_answered = False
    st.session_state.current_question_data = None
    st.rerun()

st.sidebar.markdown("### Stats 📊")
wins = st.session_state.score['wins']
losses = st.session_state.score['losses']
total_games = wins + losses
win_rate = (wins / total_games * 100) if total_games > 0 else 0
st.sidebar.metric("Win Rate", f"{win_rate:.1f}%")
st.sidebar.metric("PnL", f"${st.session_state.score['pnl']:.2f}")

if st.sidebar.button("Reset Game"):
    st.session_state.current_question_index = 0
    st.session_state.score = {'wins': 0, 'losses': 0, 'pnl': 0.0}
    st.session_state.user_answered = False
    st.session_state.current_question_data = None
    st.rerun()


# --- Load Data ---
all_questions = load_exam_data()
questions = filter_questions(all_questions, st.session_state.game_mode)

if not questions:
    st.error(f"No questions found for {st.session_state.game_mode} mode.")
    st.stop()

# Get Current Question
current_q = questions[st.session_state.current_question_index % len(questions)]
st.session_state.current_question_data = current_q


# --- Generate Mock Data (Only once per question) ---
if st.session_state.stock_df is None or st.session_state.current_question_data['id'] != current_q['id']:
    try:
        stock_data, index_data = generate_mock_data(current_q['ticker'], current_q['date'], current_q['timestamp'])
        st.session_state.stock_df = stock_data
        st.session_state.index_df = index_data
    except Exception as e:
        log_error(e, f"Data Generation Error for {current_q['id']}")
        st.error("Error generating chart data.")
        st.stop()


# --- Charting Logic ---

# Filter data up to the decision timestamp
decision_time_str = f"{current_q['date']} {current_q['timestamp']}"
decision_dt = datetime.datetime.strptime(decision_time_str, "%Y-%m-%d %H:%M")

# Ensure mock data has valid time
if not st.session_state.stock_df.empty:
    mask = st.session_state.stock_df['Time'] <= decision_dt
    display_stock = st.session_state.stock_df.loc[mask]
    display_index = st.session_state.index_df.loc[st.session_state.index_df['Time'] <= decision_dt]
else:
    display_stock = pd.DataFrame()
    display_index = pd.DataFrame()

# Create Charts
fig = make_subplots(rows=1, cols=2, shared_xaxes=True,
                    subplot_titles=(f"Stock: {current_q['ticker']} (1m)", "Market Index (^TWII)"),
                    column_widths=[0.7, 0.3])

# Stock Candlestick
fig.add_trace(go.Candlestick(x=display_stock['Time'],
                open=display_stock['Open'],
                high=display_stock['High'],
                low=display_stock['Low'],
                close=display_stock['Close'],
                name='Price'), row=1, col=1)

# VWAP Line
fig.add_trace(go.Scatter(x=display_stock['Time'], y=display_stock['VWAP'],
                         mode='lines', name='VWAP', line=dict(color='yellow', width=1.5)), row=1, col=1)

# Market Index Line
fig.add_trace(go.Scatter(x=display_index['Time'], y=display_index['Close'],
                         mode='lines', name='Index', line=dict(color='cyan')), row=1, col=2)

# Styling
fig.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=20, r=20, t=40, b=20))
fig.update_xaxes(showgrid=False)
fig.update_yaxes(showgrid=True, gridcolor='gray')

st.plotly_chart(fig, use_container_width=True)


# --- Control Panel ---
col1, col2, col3 = st.columns(3)

def handle_decision(action):
    is_correct, pnl = calculate_result(action, st.session_state.current_question_data)

    # Update Stats
    if is_correct:
        st.session_state.score['wins'] += 1
    else:
        st.session_state.score['losses'] += 1
    st.session_state.score['pnl'] += pnl

    st.session_state.user_answered = True
    st.session_state.last_result = {
        "correct": is_correct,
        "pnl": pnl,
        "explanation": st.session_state.current_question_data['explanation']
    }

if not st.session_state.user_answered:
    with col1:
        if st.button("🟢 BUY", use_container_width=True):
            handle_decision("Buy")
            st.rerun()
    with col2:
        if st.button("🔴 SELL/SHORT", use_container_width=True):
            handle_decision("Sell")
            st.rerun()
    with col3:
        if st.button("⚪ PASS", use_container_width=True):
            handle_decision("Pass")
            st.rerun()

else:
    # --- Result View ---
    result = st.session_state.last_result

    if result["correct"]:
        st.success(f"✅ Correct! PnL: {result['pnl']}%")
    else:
        st.error(f"❌ Incorrect. PnL: {result['pnl']}%")

    st.info(f"💡 Explanation: {result['explanation']}")

    if st.button("Next Level ➡️"):
        st.session_state.current_question_index += 1
        st.session_state.user_answered = False
        st.session_state.current_question_data = None
        st.session_state.stock_df = None # Force data regen
        st.rerun()
