# Data model

PostgreSQL 17, 15 tables, created by `scripts/schema.sql`.

| Table | Purpose |
|---|---|
| `users` | Logins, salted password hashes, role (manager, planner, admin) |
| `businesses` | Railway, hotels, amusement park |
| `user_businesses` | Which user may see which business |
| `locations` | Stations, hotels and the park, each belonging to a business |
| `ridership_daily` | Passengers per station, ticket type and day |
| `hotel_daily` | Rooms available, rooms booked and average rate per hotel and day |
| `park_daily` | Visitors, average wait and revenue per day |
| `weather_daily` | Temperature, rainfall and sunshine per day |
| `holidays` | Japanese public holidays |
| `events` | Seasonal events (cherry blossom, summer, autumn leaves) |
| `forecasts` | Next-week predictions, stored with the model used |
| `anomalies` | Unusual days with observed value, expected value and score |
| `data_quality_log` | Every problem the cleaning step found and what it did |
| `audit_log` | Logins, data views and refused requests |
| `reports` | Record of generated weekly reports (used once reports are built) |

## Design choices

**Uniqueness rules make the load safe to rerun.** Each daily table has a
uniqueness constraint (for example one row per date, location and ticket type in
`ridership_daily`). Loading the same file twice therefore adds nothing: the second
run loaded 0 new rows.

**Access control lives in data.** The `user_businesses` link table decides which
businesses a user can see. The default is deny: a business the user is not linked
to is refused and the refusal is written to `audit_log`.

**The database rejects impossible data.** Check constraints stop negative counts,
more rooms booked than available, and an event that ends before it starts. Roles
are limited to manager, planner and admin.

**The application uses a limited user.** The app connects as `fuji_app`, which
owns only this database, and not as the PostgreSQL superuser.