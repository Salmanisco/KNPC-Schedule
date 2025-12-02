import datetime
import pandas as pd
import streamlit as st
import numpy as np
import holidays
from streamlit_calendar import calendar



# Shift cycles starting from Oct 6 2024
A = ['Night', 'Night', 'Off', 'Off', 'Morning', 'Morning', 'Afternoon', 'Afternoon']
B = ['Morning', 'Morning', 'Afternoon', 'Afternoon', 'Night', 'Night', 'Off', 'Off']
C = ['Off', 'Off', 'Morning', 'Morning', 'Afternoon', 'Afternoon','Night', 'Night']
D = ['Afternoon', 'Afternoon', 'Night', 'Night', 'Off', 'Off', 'Morning', 'Morning']

KOC_A = ['Night', 'Off', 'Off', 'Morning']
KOC_B = ['Off', 'Off', 'Morning', 'Night']
KOC_C = ['Off', 'Morning', 'Night', 'Off']
KOC_D = ['Morning', 'Night', 'Off', 'Off']

shift_groups_dict = {
  "A": A, 
  "B": B, 
  "C": C, 
  "D": D, 
  "KOC A": KOC_A, 
  "KOC B": KOC_B, 
  "KOC C": KOC_C, 
  "KOC D": KOC_D
}

def get_shift_for_date(date, cycle: list[str]):
  """
  Returns the shift type for a given date based on the schedule pattern.
  """
  start_date = datetime.date(2024, 10, 6)
  days_since_start = (date - start_date).days
  shift_index = (days_since_start % len(cycle))
  return cycle[shift_index]


def create_schedule(start_date, end_date, cycle: list[str]):
  """
  Creates a schedule with the specified start and end date for a specific shift cycle,
  including Kuwaiti holidays.
  """
  schedule = []
  kw_holidays = holidays.KW(language='en_US')
  
  current_date = start_date
  while current_date <= end_date:
    shift = get_shift_for_date(current_date, cycle)
    holiday_name = kw_holidays.get(current_date) # Returns None if not a holiday
    schedule.append([current_date, shift, holiday_name])
    current_date += datetime.timedelta(days=1)

  df = pd.DataFrame(schedule, columns=['Date', 'Shift', 'Holiday'])
  # Ensure Date is datetime64[ns] for .dt accessor
  df['Date'] = pd.to_datetime(df['Date'])
  df['Day of Week'] = df['Date'].dt.day_name()
  
  # Fill NaN holidays with empty string for cleaner display
  df['Holiday'] = df['Holiday'].fillna('')
  
  return df[['Date', 'Day of Week', 'Shift', 'Holiday']]


def weekends(schedule_df):
  """
  Finds consecutive weekend days (Friday and Saturday) in a schedule DataFrame using vectorization.
  """
  if schedule_df.empty:
      return pd.DataFrame()

  # Create boolean masks for conditions
  is_fri = schedule_df['Day of Week'] == 'Friday'
  is_sat = schedule_df['Day of Week'] == 'Saturday'
  is_off = schedule_df['Shift'] == 'Off'
  
  # Shift to check next day
  next_is_sat = is_sat.shift(-1, fill_value=False)
  next_is_off = is_off.shift(-1, fill_value=False)

  # Condition: Current is Fri+Off AND Next is Sat+Off
  condition = is_fri & is_off & next_is_sat & next_is_off
  
  # Get indices of Fridays that satisfy the condition
  fri_indices = schedule_df.index[condition]
  
  # We want to include both the Friday and the following Saturday
  # So we take the indices and indices + 1
  all_indices = []
  for idx in fri_indices:
      all_indices.append(idx)
      all_indices.append(idx + 1)
      
  if not all_indices:
      return pd.DataFrame()
      
  return schedule_df.loc[all_indices].reset_index(drop=True)

def highlight_rows(row):
    """
    Highlights the entire row based on Shift or Holiday status.
    """
    styles = [''] * len(row)
    
    # Check for holiday first (priority)
    if row['Holiday']:
        # Gold/Orange for holidays
        return ['background-color: #fff3cd; color: #856404'] * len(row)
        
    val = row['Shift']
    if val == 'Off':
        return ['background-color: #d4edda; color: #155724'] * len(row) # Greenish
    elif val == 'Night':
        return ['background-color: #cce5ff; color: #004085'] * len(row) # Blueish
    elif val == 'Morning':
        return ['background-color: #ffffff; color: #000000'] * len(row) # White/Default
    elif val == 'Afternoon':
        return ['background-color: #f8d7da; color: #721c24'] * len(row) # Reddish
        
    return styles

st.set_page_config(
  page_title="KNPC Schedule", 
  page_icon="🛢️",
  layout="centered"
)

st.title("🛢️ KNPC Schedule")

# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. Group Selection
    st.subheader("Group Selection")
    col1, col2 = st.columns(2)
    with col1:
        company = st.selectbox("Company", ["KNPC", "KOC"])
    with col2:
        group = st.selectbox("Group", ["A", "B", "C", "D"])
    
    if company == "KNPC":
        cycle_key = group
    else:
        cycle_key = f"KOC {group}"
    
    shift_cycle = shift_groups_dict[cycle_key]
    
    st.divider()

    # 2. Date Selection
    st.subheader("Date Selection")
    today = datetime.date.today()

    if 'date_range' not in st.session_state:
        st.session_state.date_range = (today, today + datetime.timedelta(days=365))
        st.session_state.quick_select = "Next Year"

    def update_dates():
        selection = st.session_state.quick_select
        if selection == "Next Week":
            st.session_state.date_range = (today, today + datetime.timedelta(days=7))
        elif selection == "Next Month":
            st.session_state.date_range = (today, today + datetime.timedelta(days=30))
        elif selection == "Next 3 Months":
            st.session_state.date_range = (today, today + datetime.timedelta(days=90))
        elif selection == "Next 6 Months":
            st.session_state.date_range = (today, today + datetime.timedelta(days=180))
        elif selection == "Next Year":
            st.session_state.date_range = (today, today + datetime.timedelta(days=365))

    st.selectbox(
        "Quick Select:",
        ["Next Year", "Next Week", "Next Month", "Next 3 Months", "Next 6 Months", "Custom"],
        key="quick_select",
        on_change=update_dates
    )

    if st.session_state.quick_select == "Custom":
        dates = st.date_input(
          "Custom Range:",
          value=st.session_state.date_range,
          min_value=datetime.date(2020, 1, 1),
          max_value=datetime.date(2050, 12, 31),
          key="date_range"
        )
    else:
        dates = st.session_state.date_range
    
    st.divider()
    
    # 3. View Selection
    st.subheader("View Mode")
    view = st.radio(
        "Select View:", 
        ["Calendar", "Upcoming Holidays", "Long Weekends", "Full Schedule"],
        index=0
    )

# --- Main Content ---

if isinstance(dates, tuple) and len(dates) == 2:
    start_d, end_d = dates
    
    if start_d > end_d:
        st.error("Start date must be before end date.")
    else:
        schedule = create_schedule(start_date=start_d, end_date=end_d, cycle = shift_cycle)
        
        # Download Button (in Sidebar)
        with st.sidebar:
            st.divider()
            csv = schedule.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f'{company}_{group}_schedule.csv',
                mime='text/csv',
                use_container_width=True
            )

        # Render Views
        if view == "Calendar":
            st.subheader("📅 Calendar")
            
            # Prepare events for the calendar
            events = []
            for index, row in schedule.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                shift = row['Shift']
                holiday = row['Holiday']
                
                # Holiday Event
                if holiday:
                    events.append({
                        "title": f"🇰🇼 {holiday}",
                        "start": date_str,
                        "allDay": True,
                        "backgroundColor": "#FFD700", # Gold
                        "borderColor": "#DAA520",
                        "textColor": "#000000"
                    })

                # Shift Event
                color = "#808080" # Default gray
                if shift == 'Off':
                    color = "#28a745" # Green
                elif shift == 'Night':
                    color = "#007bff" # Blue
                elif shift == 'Morning':
                    color = "#ffc107" # Yellow/Orange
                    text_color = "#000000"
                elif shift == 'Afternoon':
                    color = "#dc3545" # Red

                event = {
                    "title": shift,
                    "start": date_str,
                    "allDay": True,
                    "backgroundColor": color,
                    "borderColor": color
                }
                if shift == 'Morning':
                     event["textColor"] = "#000000"
                
                events.append(event)

            calendar_options = {
                "headerToolbar": {
                    "left": "prev,next today",
                    "center": "title",
                    "right": "multiMonthYear,dayGridMonth,listMonth"
                },
                "initialView": "multiMonthYear",
                "initialDate": start_d.strftime('%Y-%m-%d'),
            }
            
            calendar(events=events, options=calendar_options)

        elif view == "Upcoming Holidays":
            st.subheader("🇰🇼 Upcoming Holidays")
            holidays_df = schedule[schedule['Holiday'] != '']
            if not holidays_df.empty:
                 st.dataframe(
                    holidays_df[['Date', 'Day of Week', 'Holiday']].style.format({'Date': '{:%d %B %Y}'}),
                    use_container_width=True,
                    column_config={
                        "Date": st.column_config.DateColumn("Date", format="DD MMMM YYYY"),
                    },
                    hide_index=True
                )
            else:
                st.info("No holidays found in the selected range.")

        elif view == "Long Weekends":
            st.subheader("🎉 Long Weekends (Fri & Sat Off)")
            weekend_schedule = weekends(schedule)
            if not weekend_schedule.empty:
                 st.dataframe(
                    weekend_schedule.style.apply(highlight_rows, axis=1).format({'Date': '{:%d %B %Y}'}),
                    use_container_width=True,
                    column_config={
                        "Date": st.column_config.DateColumn("Date", format="DD MMMM YYYY"),
                    },
                    hide_index=True
                )
            else:
                st.info("No long weekends found in this range.")

        elif view == "Full Schedule":
            st.subheader("📋 Full Schedule")
            # Apply styling to the entire row
            styled_schedule = schedule.style.apply(highlight_rows, axis=1).format({'Date': '{:%d %B %Y}'})
            
            st.dataframe(
                styled_schedule, 
                use_container_width=True,
                column_config={
                    "Date": st.column_config.DateColumn("Date", format="DD MMMM YYYY"),
                },
                hide_index=True
            )

elif isinstance(dates, tuple) and len(dates) == 1:
    st.warning("Please select an end date.")
else:
    st.error("Invalid date selection.")