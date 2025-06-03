# simulate_days.py

import re
from marl_simulation import simulate_one_day
from dqn_agent import DQNAgent


def parse_summary(summary_text):
    c  = int(re.search(r"Completed:\s*(\d+)", summary_text).group(1))
    m  = int(re.search(r"Missed:\s*(\d+)",    summary_text).group(1))
    cr = float(re.search(r"Completion Rate:\s*([\d.]+)%", summary_text).group(1))
    av = float(re.search(r"Availability:\s*([\d.]+)%",    summary_text).group(1))
    return c, m, cr, av

if __name__ == "__main__":
    DAYS = 100
    
    # 1) Instantiate the shared DQN agent once
    shared_agent = DQNAgent(state_dim=8, action_dim=7)
    # 2) Load the pretrained weights & epsilon
    shared_agent.load('./checkpoints/dqn_agent.pth')

    print("Day |  Comp | Miss | Rate (%) | Avail (%) | Cost")
    print("-------------------------------------------------")

    prev_c = prev_m = prev_cost = 0
    for day in range(1, DAYS+1):
        summary_text, day_cost = simulate_one_day()
        comp, missed, rate, avail = parse_summary(summary_text)

        # now comp, missed and day_cost are already "per-day"
        print(f"{day:3d} | {comp:5d} | {missed:4d} | {rate:8.2f} | {avail:9.2f} | {day_cost:5d}")