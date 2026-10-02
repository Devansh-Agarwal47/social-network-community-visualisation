# Data dictionary (what every column means)

All data is **synthetic** (made up by `stage1_create_dataset.py`). Emails use the reserved fake domains
`example.com/.org/.net`, so no real person is involved. "Today" inside the dataset is **2026-09-01**.

## users.csv  (1,000 people, 1,010 rows because 10 are duplicates)
| Column | Meaning | Example | Notes |
|---|---|---|---|
| user_id | unique id of the person | U0338 | the key that connections and posts point to |
| username | handle | nisha_nair24 | unique |
| full_name | first + last name | Nisha Nair | not unique (two people can share a name) |
| email | contact email | nisha_nair24@example.com | fake domain |
| age | age in years | 23 | real values are 16-60; pandas shows it as `23.0` because blanks force a decimal type |
| city | home city | Mumbai | 10 Indian cities |
| interest | main interest group | Music | Tech, Sports, Music, Food, Travel, Fashion. **Hidden ground truth** for the communities we detect later |
| account_type | kind of account | creator | personal, creator, business |
| joined_date | day the account was created | 2019-06-28 | YYYY-MM-DD |
| last_active_date | last day the user was seen | 2025-12-14 | never before joined_date |
| is_verified | verified badge | False | mostly creators and businesses |

## connections.csv  (about 3,900 friendships, 4,008 rows with errors)
Each row is one friendship = **one edge** of the graph. Users are the **vertices**.
| Column | Meaning | Example |
|---|---|---|
| connection_id | unique id of the friendship | C03731 |
| user_id_1, user_id_2 | the two friends (order does not matter, friendship is mutual) | U0336, U0427 |
| connected_on | day they became friends (never before both accounts existed) | 2025-01-31 |
| interaction_count | how much they interact; later used as the edge **weight** | 6 |

## posts.csv  (about 3,450 posts, 3,482 rows including duplicates)
| Column | Meaning | Example |
|---|---|---|
| post_id | unique id | P02013 |
| user_id | author (points to users) | U0148 |
| posted_at | date and time | 2025-06-24 11:19:10 |
| text | the post sentence | Anyone else excited about this year in tech? |
| hashtags | space-separated tags | #python #AI |
| likes, shares, comments | reactions; popular (well-connected) users get more | 4, 0, 0 |

## The planted errors (2-5% of rows in each table)
| Table | Error types | Rows affected |
|---|---|---|
| users | duplicate rows, missing age/city/email, impossible age (-5, 0, 150, 999), city spelled differently (`jaipur`, `MUMBAI`, `Bangalore`), date in another style (`15/03/2022`) | 45 of 1,010 = 4.5% |
| connections | duplicate rows, same friendship written both ways, user connected to themselves, unknown user id, missing date, dated before the accounts existed | 147 of 4,008 = 3.7% |
| posts | duplicate rows, missing text, negative likes, unknown user id, posted before the account existed, dated in the future | 129 of 3,482 = 3.7% |

The full list of planted errors is in `data/answer_key/anomalies.csv`. **Do not use it to clean the data**;
Stage 2 must find the errors from the data alone, and the key is only for checking the result.
