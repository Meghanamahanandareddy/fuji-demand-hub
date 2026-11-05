   # Requirements: Mt. Fuji Tourism Demand Hub

      ## 1. Problem statement
    

The Fuji Kyuko Group runs railways, buses, Fuji-Q Highland, and hotels around
Mt. Fuji. All of these businesses depend on the same visitors, and visitor numbers
change sharply with the season, the weather, and Japanese holidays.

Each business, however, tracks its own data separately. A railway manager sees
ridership but not hotel bookings, and a hotel manager sees reservations but not how
many visitors the park expects. Reports are often put together by hand, so they
arrive late, and a simple question such as "why did Sunday ridership jump?" means
asking someone to pull the data.

As a result, decisions about trains, buses, and staff are made with only part of the
picture. On busy days this means crowded services and long queues, and on quiet days
it means idle staff and empty vehicles.

**Goal:** a pilot system that brings the data from several businesses into one place,
forecasts next week's demand, produces weekly reports automatically, and lets
managers ask questions in plain language, so planning is based on the whole picture.

*Note: all data in this project is synthetic. It is a pilot to show an approach, not
a system built on Fuji Kyuko's real data.*

     ## 2. Users

The names below are used to represent each role in the pilot.

| Persona | Role | Main frustration |
|---|---|---|
| **Vishnu** | Business manager (hotel operations; the same role applies to railway and bus managers) | "I only find out how busy we'll be when the guests are already arriving. I can't see what the park or the trains are expecting." |
| **Meghana** | DX planner, Corporate Planning Group | "Every business sends me data in a different format, and I spend more time preparing it than analysing it." |
| **Dhiren** | System administrator | "I need to control who can see which business's data, and be able to show who looked at what." |

## 3. User stories

Priority: **Must** = needed for the pilot to work, **Should** = important, **Could** = only if time allows.

| ID | Story | Priority |
|---|---|---|
| US-01 | As a business manager, I want to log in and see a dashboard of my own business's key numbers (occupancy or ridership by day), so that I know how things are going without asking anyone. | Must |
| US-02 | As a business manager, I want to filter the dashboard by date range and location, so that I can compare busy and quiet periods. | Must |
| US-03 | As a business manager, I want to see a forecast of next week's demand, so that I can plan staff, trains, or rooms in advance. | Must |
| US-04 | As a business manager, I want to ask a question in plain language (for example, "Which day last month had the