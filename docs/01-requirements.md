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
forecasts next week's demand, flags unusual days automatically, produces weekly
reports automatically, and lets managers ask questions in plain language, so
planning is based on the whole picture.

*Note: all data in this project is synthetic. It is a pilot to show an approach, not
a system built on Fuji Kyuko's real data.*

## 2. Users

The names below are used to represent each role in the pilot.

| Persona | Role | Main frustration |
|---|---|---|
| **Vishnu** | Business manager (hotel operations; the same role applies to railway and park managers) | "I only find out how busy we'll be when the guests are already arriving. I can't see what the park or the trains are expecting." |
| **Meghana** | DX planner, Corporate Planning Group | "Every business sends me data in a different format, and I spend more time preparing it than analysing it." |
| **Dhiren** | System administrator | "I need to control who can see which business's data, and be able to show who looked at what." |

## 3. User stories

Priority: **Must** = needed for the pilot to work, **Should** = important,
**Could** = only if time allows.

Status: **Done** = built and working, **Partly** = some of it built,
**Planned** = not built yet.

| ID | Story | Priority | Status |
|---|---|---|---|
| US-01 | As a business manager, I want to log in and see a dashboard of my own business's key numbers (occupancy or ridership by day), so that I know how things are going without asking anyone. | Must | Partly (dashboard built; login is in the API, a login screen on the dashboard is planned) |
| US-02 | As a business manager, I want to filter the dashboard by date range and location, so that I can compare busy and quiet periods. | Must | Done |
| US-03 | As a business manager, I want to see a forecast of next week's demand, so that I can plan staff, trains, or rooms in advance. | Must | Done |
| US-04 | As a business manager, I want to ask a question in plain language (for example, "Which day last month had the lowest occupancy?"), so that I get an answer without waiting for an analyst. | Should | Planned |
| US-05 | As a business manager, I want a weekly report delivered automatically as a PDF or Excel file, so that I don't have to build it by hand. | Must | Done |
| US-06 | As a DX planner, I want to see all businesses side by side, so that I can understand how demand in one business affects the others. | Must | Done |
| US-07 | As a DX planner, I want to see how weather and Japanese holidays relate to demand, so that I can explain why numbers rose or fell. | Should | Done |
| US-08 | As a DX planner, I want data from each source loaded and cleaned automatically, so that I can spend my time on analysis. | Must | Done |
| US-09 | As an admin, I want to give each user a role that limits which businesses' data they can see, so that people only see what they should. | Must | Done (API, verified by tests) |
| US-10 | As an admin, I want an audit log of who viewed data, ran questions, or downloaded reports, so that I can review activity if something goes wrong. | Should | Partly (logins, data views and refused requests are logged; questions and downloads come with those features) |
| US-11 | As a DX planner, I want unusual days flagged automatically, so that I notice events such as a typhoon without searching for them. | Should | Done |

## 4. Scope

**In scope (pilot)**
- Three business units: **railway**, **hotels**, and the **amusement park**
- Synthetic data covering about three years of daily records (January 2024 to October 2026)
- Data pipeline that cleans raw files and records every fix in a data-quality log
- Per-business dashboard with date and location filters
- One-week-ahead demand forecast per business, with several models compared
- Anomaly detection that flags unusual days
- Cross-business view (all three businesses side by side)
- Weather and Japanese holiday data as demand drivers
- Natural-language question assistant (read-only database access)
- Automatic weekly PDF/Excel report per business
- Role-based access (business manager, DX planner, admin) with an audit log
- English interface

**Stretch goals (only if time allows)**
- Deployment on AWS
- Automated tests run on every commit
- Weather forecast feed for the forecasting model

**Out of scope**
- Fuji Kyuko's real data or any connection to their live systems
- Real-time data feeds
- Mobile app
- Customer-facing features (this tool is for internal managers and planners)
- Japanese-language interface

## 5. Data sources

All data sets are generated by a script in this project. None come from Fuji Kyuko.

| Data set | Business | Main fields | How it's produced | Frequency |
|---|---|---|---|---|
| Railway ridership | Railway | date, station, passengers, ticket type | Synthetic, with weekday, season, and holiday patterns | Daily |
| Hotel reservations | Hotels | date, hotel, rooms booked, rooms available, average room rate | Synthetic, with seasonal peaks and weekend effects | Daily |
| Park visitors | Amusement park | date, visitors, average wait time, revenue | Synthetic, with seasonal peaks and a rain effect | Daily |
| Weather | Shared | date, temperature, rainfall, sunshine hours | Synthetic, with realistic seasonal range and one planted typhoon week | Daily |
| Japanese holidays | Shared | date, holiday name | Generated from a holiday calendar | Yearly |
| Seasonal events | Shared | date range, event name (for example cherry blossom or autumn leaves season) | Hand-written list | Yearly |

Hotel names are fictional. Station names follow the public Fujikyuko Line.

The raw files deliberately contain realistic problems (mixed date formats, blank
values, duplicate rows, inconsistent station names, rooms booked above capacity) so
that the cleaning step has real work to do.

## 6. Non-functional requirements

**Security**
- Every user logs in, and each role sees only the businesses it is allowed to see
- Passwords are stored hashed, never in plain text
- Database credentials are kept in environment variables, not in code
- The question assistant can only read data, never change or delete it
- Every login, data view, refused request, question, and report download is written to an audit log

**Reliability**
- The data load can be rerun safely without creating duplicate records
- Invalid or missing data is flagged and logged, not silently ignored

**Performance**
- Dashboard pages load in under 3 seconds for about three years of daily data
- The weekly report generates in under 1 minute

**Data privacy**
- All data is synthetic and contains no personal information

**Maintainability**
- Code is organised in separate modules (data, forecasting, API, dashboard)
- Core logic is covered by automated tests

## 7. Success measures

| Measure | Target | Result so far |
|---|---|---|
| Forecast accuracy | Average error under 15% on a held-out final month of data | **Met:** 6.7% railway, 7.6% hotels, 12.6% park (October 2026) |
| Anomaly detection | The planted typhoon week is flagged in every business | **Met:** 16 to 20 Sep 2025 flagged in railway, hotels and park |
| Access control | A hotel manager cannot view railway data (verified by a test) | **Met:** automated test passes |
| Data load | Rerunning the load adds no duplicates | **Met:** second run loads 0 new rows. Load time is not yet measured |
| Audit log | Logins, questions, and downloads each appear in the log | **Partly met:** logins, data views and refused requests are logged; questions and downloads are planned |
| Report automation | Weekly reports for all businesses generated with one command and no manual editing | Planned |
| Question assistant | At least 8 of 10 prepared test questions answered correctly | Planned |
| Dashboard speed | Pages load in under 3 seconds | Not yet measured |