# Madrid Bike-Sharing Simulation
A real-time simulation of bike-sharing activity in Madrid using historical trip data and live map visualizations. This project displays station activity across a 24-hour period compressed into a 5-minute live simulation using Dash and Plotly.

Bike-sharing systems are becoming an essential part of city transportation, helping to reduce traffic and pollution. However, a significant challenge for these systems is to ensure that there are enough bikes available at each station when users need them. This dissertation focuses on improving bike redistribution to maintain stations balanced, allowing more people to benefit from the service
without waiting.

The study employs multi-agent reinforcement learning, a form of artificial intelligence, to address this issue, treating each bike station as a separate decision-maker. These stations learn to move bikes between each other using a method called Deep Q-Network (DQN). The goal is to move bikes during times when demand is lower, during off-peak hours, so the stations are better prepared for periods of high demand.

The method is tested using computer simulations with data from the Madrid bike-sharing system. Different scenarios are created by changing the initial bike count per station at the beginning of the simulation day. The results demonstrate that the multi-agent DQN algorithm adapts effectively over time, improving key performance metrics, including missed trips, trip completion rates, and station availability. Scenarios with moderate initial bike levels (30 and 40 bikes per station) offer the best balance between user service quality and operational cost. The approach demonstrates the potential of reinforcement learning for dynamic data-driven management in bike-sharing networks, outperforming a baseline method without redistribution.

This work contributes to the field by combining multi-agent reinforcement learning approaches with urban mobility challenges and highlighting practical aspects for implementing intelligent redistribution strategies. Future work will focus on integrating real-time demand, conducting pilot tests in operational systems, and developing adaptive infrastructure planning to improve flexibility and resilience.

## Detailed information
- https://hackmd.io/@AudlaQKrRO-pFcMAxcX4Fg/SJXLaazayl
---

## Simulation framework
<img width="1259" height="665" alt="may_5th_during_simulation" src="https://github.com/user-attachments/assets/d5fc11dc-a47d-46da-96f6-574983150676" />
<img width="1256" height="671" alt="may_11th_after_simulation" src="https://github.com/user-attachments/assets/02c95f22-7c8a-46d0-8249-cb97214ad56e" />
---

## Dataset
- `tripdata_2022.csv`: full Madrid dataset for 2022
- `all_stations.csv`: contains all station locations (lat/lon), names, and IDs
- `all_trips_05_05.csv` & `all_trips_05_11.csv`: real bike trip with:
  - `start_time`, `end_time`
  - `start_station_id`, `end_station_id`
---

## Setup Instructions
- make sure you first have `all_stations.csv` , `all_trips_05_05.csv` and `all_trips_05_11.csv` files
- then run `python app.py`
