import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import os
from collections import deque

# ==================== Replay Buffer ====================#
class ReplayBuffer:
    def __init__(self, capacity):
        self.buffer = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, done):
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size):
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = map(np.array, zip(*batch))
        return states, actions, rewards, next_states, dones

    def __len__(self):
        return len(self.buffer)

# ==================== Q-Network (Neural Net) ====================#
class QNetwork(nn.Module):
    def __init__(self, input_dim=8, output_dim=7, hidden_dim=128):
        super(QNetwork, self).__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, output_dim)

    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        return self.fc3(x)

# ==================== DQN Agent (Shared) ====================#
class DQNAgent:
    def __init__(self, state_dim, action_dim, buffer_capacity=50000,
                 batch_size=64, lr=5e-5, gamma=0.99, target_update_freq=250,
                 device=None):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.batch_size = batch_size
        self.gamma = gamma
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Main and target networks
        self.q_network = QNetwork(state_dim, action_dim).to(self.device)
        self.target_network = QNetwork(state_dim, action_dim).to(self.device)
        self.target_network.load_state_dict(self.q_network.state_dict())
        self.target_network.eval()

        self.optimizer = optim.Adam(self.q_network.parameters(), lr=lr)
        self.replay_buffer = ReplayBuffer(buffer_capacity)

        # Epsilon-greedy
        self.epsilon = 1.0
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.9995

        self.learn_step_counter = 0
        self.target_update_freq = target_update_freq

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        torch.save({
            'q_net'      : self.q_network.state_dict(),
            'target_net' : self.target_network.state_dict(),
            'opt'        : self.optimizer.state_dict(),
            'epsilon'    : self.epsilon
        }, path)

    def load(self, path: str):
        if not os.path.isfile(path):
            return
        ckpt = torch.load(path, map_location=lambda s, l: s)  # CPU/GPU agnostic
        self.q_network.load_state_dict(ckpt['q_net'])
        self.target_network.load_state_dict(ckpt['target_net'])
        self.optimizer.load_state_dict(ckpt['opt'])
        self.epsilon = ckpt.get('epsilon', self.epsilon)
        print(f"Loaded checkpoint '{path}' (ε={self.epsilon:.3f})")

    def select_action(self, state):
        if random.random() < self.epsilon:
            return random.randrange(self.action_dim)
        else:
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            with torch.no_grad():
                q_vals = self.q_network(state_tensor)
            return q_vals.argmax().item()

    def store_transition(self, state, action, reward, next_state, done):
        self.replay_buffer.push(state, action, reward, next_state, done)

    def update(self):
        if len(self.replay_buffer) < self.batch_size:
            return
        
        # 1) Sample a fresh batch
        states_np, actions_np, rewards_np, next_states_np, dones_np = \
            self.replay_buffer.sample(self.batch_size)
        # 2) Convert to brand‐new tensors via torch.tensor(...)
        states      = torch.tensor(states_np,      dtype=torch.float32, device=self.device)
        actions     = torch.tensor(actions_np,     dtype=torch.int64,   device=self.device).unsqueeze(1)
        rewards     = torch.tensor(rewards_np,     dtype=torch.float32, device=self.device).unsqueeze(1)
        next_states = torch.tensor(next_states_np, dtype=torch.float32, device=self.device)
        dones       = torch.tensor(dones_np,       dtype=torch.float32, device=self.device).unsqueeze(1)

        # Current Q(s,a)
        q_values = self.q_network(states).gather(1, actions)

        # Compute targets using target network without grad tracking
        with torch.no_grad():
            next_q_vals = self.target_network(next_states).max(1)[0].unsqueeze(1)
            target_q    = rewards + self.gamma * next_q_vals * (1 - dones)

        # Compute loss
        loss = nn.MSELoss()(q_values, target_q)

        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        # Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        # Update target network
        self.learn_step_counter += 1
        if self.learn_step_counter % self.target_update_freq == 0:
            self.target_network.load_state_dict(self.q_network.state_dict())

# ==================== StationAgent Wrapper ====================#
class StationAgent:
    def __init__(self, station_id, agent: DQNAgent):
        self.station_id = station_id
        self.agent      = agent
        self.last_state = None
        self.last_action= None

    def observe_and_act(self, observation):
        state = self._obs_to_vector(observation)
        action = self.agent.select_action(state)
        self.last_state  = state
        self.last_action = action
        return action

    def record(self, reward, next_observation, done):
        next_state = self._obs_to_vector(next_observation)
        self.agent.store_transition(self.last_state,
                                    self.last_action,
                                    reward,
                                    next_state,
                                    done)

    def learn(self):
        self.agent.update()

    def _obs_to_vector(self, obs: dict):
        return np.array([
            obs['current_bike_count'],
            obs['historical_demand_next_hr'],
            obs['historical_inflow_next_hr'],
            obs['outgoing_5hr'],
            obs['was_empty_ratio'],
            obs['was_full_ratio'],
            obs['current_hour'],
            0 if obs.get('previous_action','do_nothing')=='do_nothing' else 1
        ], dtype=np.float32)
