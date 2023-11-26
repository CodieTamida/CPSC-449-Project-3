# CPSC 449 Project 3
* [Project Document](https://docs.google.com/document/d/1szW1jXacdYrjgVPZvZnSmS9IESH4BIxatiCl_-Np4Go/edit)

We have forked a team member’s Project 2 as a baseline, which was then modified to meet the requirements mentioned in the prompt for Project 3.

## How to run the services and initialize their databases
1. To run the services, open a terminal in with the project's root as the current directory and run:
   ```bash
   foreman start
   ```
2. In a new terminal, initialize the databases with these commands:
   ```bash
   ./users/var/updateDB.sh
   cd enroll/var/ && python3 catalog.py
   ```
Detailed instructions on how to access the API endpoints can be found in the project document under `Accessing API Endpoints`.
