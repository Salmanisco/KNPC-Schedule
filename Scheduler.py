import datetime
import pandas as pd
import streamlit as st
import numpy as np
import holidays

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
  kw_holidays = holidays.KW()
  
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

cycle = st.radio("Choose a group: ", [group for group in shift_groups_dict], horizontal=True)
shift_cycle = shift_groups_dict[cycle]

today = datetime.date.today()
next_week = today + datetime.timedelta(days = 7)

dates = st.date_input(
  "Select your dates: ",
  value= (today, next_week),
  min_value=datetime.date(2020, 1, 1),
  max_value=datetime.date(2030, 12, 31)
)

if isinstance(dates, tuple) and len(dates) == 2:
    start_d, end_d = dates
    
    if start_d > end_d:
        st.error("Start date must be before end date.")
    else:
        schedule = create_schedule(start_date=start_d, end_date=end_d, cycle = shift_cycle)
        
        st.subheader("📅 Schedule")
        
        # Apply styling to the entire row
        styled_schedule = schedule.style.apply(highlight_rows, axis=1)
        
        st.dataframe(
            styled_schedule, 
            use_container_width=True,
            column_config={
                "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            },
            hide_index=True
        )

        # Download button
        csv = schedule.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Schedule as CSV",
            data=csv,
            file_name=f'knpc_schedule_{cycle}_{start_d}_{end_d}.csv',
            mime='text/csv',
        )

        # Holidays Section
        holidays_df = schedule[schedule['Holiday'] != '']
        if not holidays_df.empty:
             st.subheader("🇰🇼 Upcoming Holidays")
             st.dataframe(
                holidays_df[['Date', 'Day of Week', 'Holiday']],
                use_container_width=True,
                column_config={
                    "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                },
                hide_index=True
            )

        weekend_schedule = weekends(schedule)

        st.divider()

        st.subheader("🎉 Long Weekends (Fri & Sat Off)")
        if not weekend_schedule.empty:
             st.dataframe(
                weekend_schedule.style.apply(highlight_rows, axis=1),
                use_container_width=True,
                column_config={
                    "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                },
                hide_index=True
            )
        else:
            st.info("No long weekends found in this range.")

elif isinstance(dates, tuple) and len(dates) == 1:
    st.warning("Please select an end date.")
else:
    st.error("Invalid date selection.")