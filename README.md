# Ambulance-task-offloading-in-VEC-using-Genetic-Algorithm
Developed an intelligent ambulance routing system using Genetic Algorithm and Vehicular Edge Computing to minimize response time. It dynamically selects optimal hospitals based on traffic, distance, beds, and specialists, and uses Yen’s K-Shortest Path for real-time rerouting, validated using SUMO simulation.


## 🎯 Objectives
- Reduce ambulance travel time
- Select optimal hospital based on multiple factors
- Enable real-time rerouting in dynamic traffic
- Use edge computing for faster decision making


## ⚙️ Tech Stack
- **Languages:** Python  
- **Simulation Tool:** SUMO (Simulation of Urban Mobility)  
- **Algorithms:**  
  - Genetic Algorithm (GA)  
  - Yen’s K-Shortest Path Algorithm  
  - Dijkstra’s Algorithm 
- **Libraries:** TraCI (SUMO control interface), NumPy, Pandas 


## 🔄 Working Methodology
1. Ambulance enters simulation  
2. RSU detects ambulance  
3. GA evaluates hospitals using fitness function  
4. Best hospital is selected  
5. Yen’s algorithm generates alternate paths  
6. Dynamic rerouting based on congestion   


