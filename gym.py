import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import time

# Internal Modules
from game_logic import load_exam_data, filter_questions, get_real_data
from logger import log_error

# Set Page Config
st.set_page_config(layout="wide", page_title="Sniper Gym (Real-World)")

# --- Initialize Session State ---
if 'current_question_index' not in st.session_state:
    st.session_state.current_question_index = 0
if 'score' not in st.session_state:
    st.session_state.score = {'wins': 0, 'losses': 0, 'pnl': 0.0}
if 'user_answered' not in st.session_state:
    st.session_state.user_answered = False
if 'current_question_data' not in st.session_state:
    st.session_state.current_question_data = None
if 'stock_df' not in st.session_state:
    st.session_state.stock_df = None
if 'index_df' not in st.session_state:
    st.session_state.index_df = None
if 'scenario_stats' not in st.session_state:
    st.session_state.scenario_stats = {}

# --- Sidebar ---
st.sidebar.title("Sniper Gym 🎯")
st.sidebar.caption("Real-World Edition")

# Stats
wins = st.session_state.score['wins']
losses = st.session_state.score['losses']
total_games = wins + losses
win_rate = (wins / total_games * 100) if total_games > 0 else 0
st.sidebar.metric("Win Rate", f"{win_rate:.1f}%")
st.sidebar.metric("PnL Accum.", f"{st.session_state.score['pnl']:.2f}%")

if st.session_state.scenario_stats:
    st.sidebar.markdown("---")
    st.sidebar.markdown("#### Scenario Stats")
    for s_type, stats in st.session_state.scenario_stats.items():
        wr = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
        st.sidebar.text(f"{s_type}: {wr:.0f}% ({stats['wins']}/{stats['total']})")

if st.sidebar.button("Reset Game"):
    st.session_state.current_question_index = 0
    st.session_state.score = {'wins': 0, 'losses': 0, 'pnl': 0.0}
    st.session_state.user_answered = False
    st.session_state.current_question_data = None
    st.session_state.scenario_stats = {}
    st.session_state.stock_df = None
    st.rerun()

# --- Load Data ---
all_questions = load_exam_data()
questions = filter_questions(all_questions, "Real")

if not questions:
    st.error("No scenarios found. Please run 'hunter.py' to generate questions.")
    st.stop()

# Get Current Question
current_q = questions[st.session_state.current_question_index % len(questions)]
st.session_state.current_question_data = current_q

# --- Fetch Real Data ---
if st.session_state.stock_df is None or st.session_state.current_question_data['id'] != current_q['id']:
    with st.spinner(f"Fetching real data for {current_q['ticker']}..."):
        stock_data, index_data = get_real_data(current_q['ticker'], current_q['date'])

        if stock_data.empty:
            st.error(f"Failed to fetch data for {current_q['ticker']} on {current_q['date']}. Likely > 30 days old or API issue.")
            # Skip button
            if st.button("Skip Question"):
                st.session_state.current_question_index += 1
                st.session_state.stock_df = None
                st.rerun()
            st.stop()

        st.session_state.stock_df = stock_data
        st.session_state.index_df = index_data

# --- Prepare Chart Data ---
# Decision Time
# current_q['timestamp'] is "HH:MM" (e.g., "09:30") or "HH:MM:SS"
ts_str = current_q['timestamp']
if len(ts_str) == 5: ts_str += ":00"
decision_time_str = f"{current_q['date']} {ts_str}"
# Parse using pandas to ensure timezone awareness match
decision_dt = pd.to_datetime(decision_time_str).tz_localize("Asia/Taipei")

# Convert Time col to datetime if not already (it should be from get_real_data)
# get_real_data returns 'Time' column localized to Asia/Taipei
df = st.session_state.stock_df
idx_df = st.session_state.index_df

# Filter Data for Display
# If Blind Mode: Show only up to decision_dt
# If Reveal Mode: Show up to decision_dt + 30 mins
if st.session_state.user_answered:
    end_view = decision_dt + datetime.timedelta(minutes=30)
else:
    end_view = decision_dt

mask = df['Time'] <= end_view
display_stock = df.loc[mask]

# Ensure we have data
if display_stock.empty:
    st.error("No data points found before decision time. Check data source.")
    st.stop()

# Filter Index
if not idx_df.empty:
    mask_idx = idx_df['Time'] <= end_view
    display_index = idx_df.loc[mask_idx]
else:
    display_index = pd.DataFrame()

# --- Plotting ---
fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    vertical_spacing=0.05, row_heights=[0.7, 0.3],
                    subplot_titles=(f"{current_q['ticker']} - Price Action", "Market Index (^TWII)"))

# Candlestick
fig.add_trace(go.Candlestick(x=display_stock['Time'],
                open=display_stock['Open'],
                high=display_stock['High'],
                low=display_stock['Low'],
                close=display_stock['Close'],
                name='Price'), row=1, col=1)

# VWAP
if 'VWAP' in display_stock.columns:
    fig.add_trace(go.Scatter(x=display_stock['Time'], y=display_stock['VWAP'],
                             mode='lines', name='VWAP', line=dict(color='orange', width=2)), row=1, col=1)

# Decision Line
fig.add_vline(x=decision_dt.timestamp() * 1000, line_width=1, line_dash="dash", line_color="white", row=1, col=1)
fig.add_vline(x=decision_dt.timestamp() * 1000, line_width=1, line_dash="dash", line_color="white", row=2, col=1)

# Index
if not display_index.empty:
    fig.add_trace(go.Scatter(x=display_index['Time'], y=display_index['Close'],
                             mode='lines', name='Index', line=dict(color='cyan')), row=2, col=1)

fig.update_layout(height=600, xaxis_rangeslider_visible=False, template="plotly_dark",
                  margin=dict(l=20, r=20, t=40, b=20),
                  legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0.5, xanchor="center"))
fig.update_yaxes(showgrid=True, gridcolor='gray')

st.plotly_chart(fig, use_container_width=True)


# --- Game Logic: Calculate Real PnL ---
def calculate_real_outcome(action, stock_full_df, decision_dt):
    # Get price at decision
    try:
        entry_row = stock_full_df.loc[stock_full_df['Time'] == decision_dt]
        if entry_row.empty:
            # Fallback to nearest
            entry_row = stock_full_df.loc[stock_full_df['Time'] <= decision_dt].iloc[-1:]

        entry_price = entry_row['Close'].values[0]

        # Get exit price (e.g., 10 mins later)
        exit_dt = decision_dt + datetime.timedelta(minutes=10)
        exit_row = stock_full_df.loc[stock_full_df['Time'] >= exit_dt]

        if exit_row.empty:
            exit_price = stock_full_df.iloc[-1]['Close'] # End of data available
        else:
            exit_price = exit_row.iloc[0]['Close']

        # Calculate raw return
        raw_ret = (exit_price - entry_price) / entry_price * 100

        pnl = 0.0
        is_win = False

        if action == "Buy":
            pnl = raw_ret
            is_win = pnl > 0
        elif action == "Sell":
            pnl = -raw_ret
            is_win = pnl > 0
        elif action == "Pass":
            pnl = 0.0
            # Pass is correct if correct_action was Pass or if taking the trade would lose money
            # But we compare against "correct_action" from hunter for "Correctness"
            # However, hunter's correct_action is heuristic.
            # Real PnL is truth.
            pass

        return pnl, entry_price, exit_price

    except Exception as e:
        log_error(e, "calculate_real_outcome")
        return 0.0, 0.0, 0.0

# --- Control Panel ---
col1, col2, col3 = st.columns(3)

def handle_decision(action):
    # 1. Check against Hunter's "Theoretical Correctness" (for educational purpose)
    theory_correct = action == current_q['correct_action']

    # 2. Calculate Real PnL
    pnl, entry, exit_p = calculate_real_outcome(action, st.session_state.stock_df, decision_dt)

    # Update Stats
    if pnl > 0:
        st.session_state.score['wins'] += 1
    elif pnl < 0:
        st.session_state.score['losses'] += 1

    # Pass counts as win if theory said Pass? Or neutral?
    # If Pass, PnL is 0.

    st.session_state.score['pnl'] += pnl

    # Scenario Stats
    s_type = current_q.get("scenario_type", "General")
    if s_type not in st.session_state.scenario_stats:
        st.session_state.scenario_stats[s_type] = {"wins": 0, "total": 0}
    st.session_state.scenario_stats[s_type]["total"] += 1
    if pnl > 0 or (action == "Pass" and theory_correct):
        st.session_state.scenario_stats[s_type]["wins"] += 1

    st.session_state.user_answered = True
    st.session_state.last_result = {
        "action": action,
        "pnl": pnl,
        "entry": entry,
        "exit": exit_p,
        "theory_correct": theory_correct,
        "explanation": current_q['explanation']
    }

if not st.session_state.user_answered:
    with col1:
        if st.button("🟢 BUY", use_container_width=True):
            handle_decision("Buy")
            st.rerun()
    with col2:
        if st.button("🔴 SELL", use_container_width=True):
            handle_decision("Sell")
            st.rerun()
    with col3:
        if st.button("⚪ PASS", use_container_width=True):
            handle_decision("Pass")
            st.rerun()

else:
    # --- Result View ---
    res = st.session_state.last_result

    # Header
    if res['pnl'] > 0:
        st.success(f"✅ PROFIT! PnL: +{res['pnl']:.2f}%")
    elif res['pnl'] < 0:
        st.error(f"❌ LOSS! PnL: {res['pnl']:.2f}%")
    else:
        st.info("⚪ No PnL impact.")

    st.markdown(f"**Scenario:** {current_q['scenario_type']}")
    st.markdown(f"**Explanation:** {res['explanation']}")

    st.caption(f"Entry: {res['entry']:.1f} | Exit (10m): {res['exit']:.1f}")

    if st.button("Next Scenario ➡️", type="primary", use_container_width=True):
        st.session_state.current_question_index += 1
        st.session_state.user_answered = False
        st.session_state.current_question_data = None
        st.session_state.stock_df = None
        st.rerun()
