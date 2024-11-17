import datetime
import pandas as pd
import streamlit as st
import numpy as np

# Shift cycles starting from Oct 6 2024 (it is used in the get_shift_for_date() function)
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

  Args:
    date: The date for which to retrieve the shift.
    shift: The list of shift types. (A, B, C, D (example: A = ['Night', 'Night', 'Off', 'Off', 'Morning', 'Morning', 'Afternoon', 'Afternoon'])

  Returns:
    The shift type (Morning, Afternoon, Night, Off) for the given date.
  """

  start_date = datetime.date(2024, 10, 6)

  days_since_start = (date - start_date).days
  shift_index = (days_since_start % len(cycle))
  return cycle[shift_index]


def create_schedule(start_date, end_date, cycle: list[str]):
  """

  Creates a schedule with the specified start and end date for a specific shift cycle

  Args:
    start_date: The starting date of the schedule.
    end_date: The ending date of the schedule.
    cycle: The list of shift types. (A, B, C, D (example: A = ['Night', 'Night', 'Off', 'Off', 'Morning', 'Morning', 'Afternoon', 'Afternoon'])

  Returns:
    A Pandas DataFrame containing the schedule.

  """

  schedule = []

  current_date = start_date
  while current_date < end_date:
    shift = get_shift_for_date(current_date, cycle)
    schedule.append([current_date, shift])
    current_date += datetime.timedelta(days=1)

  df = pd.DataFrame(schedule, columns=['Date', 'Shift'])
  df['Date'] = pd.to_datetime(df['Date'], format="%d/%m/%Y")
  df['Day of Week'] = df['Date'].dt.day_name()
  return df[['Date', 'Day of Week', 'Shift']]


def weekends(schedule_df):
  """
  Finds consecutive weekend days (Friday and Saturday) in a schedule DataFrame.

  Args:
    schedule_df: A Pandas DataFrame with 'Date', 'Shift', and 'Day of Week' columns.

  Returns:
    A DataFrame containing rows with consecutive weekend days.
  """
  consecutive_weekends = []
  for i in range(len(schedule_df) - 1):
    current_row = schedule_df.iloc[i]
    next_row = schedule_df.iloc[i + 1]

    if (current_row['Day of Week'] == 'Friday' or current_row['Day of Week'] == 'Saturday') and \
       current_row['Shift'] == 'Off' and \
       (next_row['Day of Week'] == 'Friday' or next_row['Day of Week'] == 'Saturday') and \
       next_row['Shift'] == 'Off':
        consecutive_weekends.append(current_row)
        consecutive_weekends.append(next_row)
  return pd.DataFrame(consecutive_weekends)


st.set_page_config(
  page_title="KNPC Schedule", 
  page_icon="🛢️"
)

st.title("KNPC Schedule")

cycle = st.radio("Choose a group: ", [group for group in shift_groups_dict], horizontal=True)
shift_cycle = shift_groups_dict[cycle]

today = datetime.datetime.now()
next_week = today + datetime.timedelta(days = 7)

dates = st.date_input(
  "Select your dates: ",
  value= (today, next_week)
)

schedule = create_schedule(start_date=dates[0], end_date=dates[1], cycle = shift_cycle)
st.subheader("Schedule")
st.table(schedule)

weekend_schedule = weekends(schedule)

st.divider()

st.subheader("Weekends!")
st.table(weekend_schedule)