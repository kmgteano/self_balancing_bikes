# -*- coding: utf-8 -*-
import csv 
import os
import copy
import sys 
import random

random.seed("Jul-31-2014")

"""
Created on Thu Jul 31 18:09:55 2014

Creates a simulation for Citi-bike rebalancing 

@author: root
"""


# Read in the station capacity with the station name as a dict
# note: input file generated by Computed_capacity.R
station_cap = {}
station_capacity_file = "data/station_cap.csv"
with open(station_capacity_file, 'rb') as f:
        reader = csv.DictReader(f)       
        for row in reader:
            station_cap[row["station.name"]] = int(row["station_capacity"])

# Read in actual available bikes at 4am on each day at each station given by historical API dump
# note: input file generated by filter_availability.py and availability_jake_edit.R
daily_avail = {}
num_days_seen = {}
running_avail_sum = {}
station_list = set()
station_available_file = "data/station_availability.csv"
with open(station_available_file, 'rb') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row["ymd"] in daily_avail:
                daily_avail[row["ymd"]] = {}
            daily_avail[row["ymd"]][row["station.name"]] = int(row["available_bikes"])
            station_list.add(row["station.name"])
            # keep running average of station availability at 4am across all days
            if row["station.name"] not in num_days_seen:
                num_days_seen[row["station.name"]] = 0
                running_avail_sum[row["station.name"]] = 0
            num_days_seen[row["station.name"]] += 1
            running_avail_sum[row["station.name"]] += float(row["available_bikes"])

# compute average availability at 4am for each station
average_daily_avail = {}                
for station in running_avail_sum:
    average_daily_avail[station] = running_avail_sum[station] / num_days_seen[station]
            
# Read in the proximity as a dict, storing the closest three stations and their proximities 
# note: input file generated by unified R script
station_prox = {}
station_prox_list = []
station_prox_file = "data/stationprox.csv"
with open(station_prox_file, 'rb') as f:
        reader = csv.DictReader(f)
        for row in reader:
            station = row["target"]
            if not station in station_prox:
                station_prox[station] = {}
                station_prox[station][station] = 0
            
            station_prox[station][row['closest.1']] = float(row["prox.1"])
            station_prox[station][row['closest.2']] = float(row["prox.2"])
            station_prox[station][row['closest.3']] = float(row["prox.3"])

# read in a flag for simulation strategy
# "greedy": greedy re-routing to best nearby station on start and destination
# "rider": rider flow only, ignoring vans
if len(sys.argv) < 5:
    print "usage: %s <strategy>" % sys.argv[0]
    exit_string = "please enter a simulation strategy, either 'greedy' or 'rider'" + "\nand a time frame for resetting, either 'daily', 'weekly', \n'monthly', or 'once' which resets the system only once randomly"
    print exit_string
    sys.exit(1)

strategy = sys.argv[1]
reset_time = sys.argv[2]
willing_rebalance = sys.argv[3]
trip_duration = sys.argv[4]
if strategy != "greedy" and strategy != "rider":
    print "%s is not a valid strategy" % strategy
    sys.exit(1)

if reset_time != "weekly" and reset_time != "monthly" and reset_time != "once":
    print "%s is not a valid time frame" % reset_time
    sys.exit(1)

if willing_rebalance != "random" and willing_rebalance != "night" and willing_rebalance != "day" and willing_rebalance != "all":
    print "%s is not a valid rebalancing behavior" % willing_rebalance

if trip_duration != "instant" and trip_duration != "approximate":
    print "%s is not a valid trip duration" % trip_duration

# open input file with actual trips: start station, start time, and end station

trips_sim_file = "data/trips_sim.csv"
with open(trips_sim_file, 'rb') as f:
        reader = csv.DictReader(f)

        # track previous reset date
        last_reset_date = ""
        print_this = False

        # dictionary to map station name to current availability
        availability = {}

        # loop over each actual trip
        for row in reader:
            if (willing_rebalance == "random" and random.randint(0,1) == 0):
                continue

            start_station = row["start.station.name"]
            end_station = row["end.station.name"]

            # extract year-month-day in d, time in t, and hour of day
            d, t = row["starttime"].split()
            hour = int(t.split(':')[0])
            reset = False

            if (willing_rebalance == "day" and hour < 6 and hour >= 12):
                continue

            if (willing_rebalance == "night" and hour >= 6 and hour < 12):
                continue

            if start_station == "DeKalb Ave & Skillman St" or end_station == "DeKalb Ave & Skillman St":
                continue

            #            
            # Set availability using actual availability at 4am
            #
            # throw out initial trips before 4am on first day seen
            if last_reset_date == "" and hour < 4:
                continue
            # if this trip is after 4am and we haven't yet reset today
            if reset_time == "daily" and hour >= 4 and last_reset_date != d:
                last_reset_date = d
                reset = True
            elif reset_time == "weekly" and hour >= 4 and last_reset_date != d:
                
                if last_reset_date != "":
                    w = int(d.split('-')[2])
                    w_last = int(str(last_reset_date).split('-')[2])
                if last_reset_date == "" or int(w / 7) != int(w_last / 7):
                    last_reset_date = d
                    reset = True
            
            elif reset_time == "monthly" and hour >= 4 and last_reset_date != d:

                if last_reset_date != "":
                    m = int(d.split('-')[1])
                    m_last = int(str(last_reset_date).split('-')[1])
                if last_reset_date == "" or m != m_last:
                    last_reset_date = d
                    reset = True
            
            else:
                if (random.randint(0,1) == 1) and last_reset_date == "":
                    last_reset_date = d
                    reset = True

                # if not d in daily_avail:
                #     continue
            if reset == True:
                for station in station_list:
                    if d in daily_avail and station in daily_avail[d]:
                        # set to availability of this station at 4am on this day
                        availability[station] = daily_avail[d][station] 
                    else:
                        # Set to that station's average at 4am across all days
                        availability[station] = average_daily_avail[station]
                reset = False

            #            
            # Set rerouted stations: end station
            #
            # compute availability at actual end station
            stationpercent_end = float(availability[end_station])/station_cap[end_station]
            # if the actual destination is congested, attempt to re-route
            if strategy == "greedy" and stationpercent_end > .8:
                # find nearby station with lowest availability by taking running min
                current_min = stationpercent_end
                current_winner = end_station
                for station in station_prox[end_station]:
                    if station in availability and station in station_cap:
                        altstationpercent = float(availability[station])/station_cap[station]
                        if current_min > altstationpercent:
                            current_min = altstationpercent
                            current_winner = station
                rerouted_end_station = current_winner
            else:
                # otherwise keep original destination
                rerouted_end_station = end_station
            if availability[rerouted_end_station] == station_cap[rerouted_end_station]:
                # throw out trip if rerouted station is full
                rerouted_end_station = "NA"
            
            #
            # set rerouted stations: start station
            # 
            # compute availability at the actual start station
            stationpercent_start = float(availability[start_station])/station_cap[start_station]
            # if the actual origin is starved, attempt to re-route
            if strategy == "greedy" and stationpercent_start < .2:
                # find nearby station with highest availability by taking running max
                current_max = stationpercent_start
                current_winner = start_station
                for station in station_prox[start_station]:
                    if station in availability and station in station_cap:
                        altstationpercent = float(availability[station])/station_cap[station]
                        if current_max < altstationpercent:
                            current_max = altstationpercent
                            current_winner = station
                rerouted_start_station = current_winner
            else:
                # otherwise keep original destination
                rerouted_start_station = start_station
            if availability[rerouted_start_station] == 0:
                # throw out trip if rerouted station is empty
                rerouted_start_station = "NA" 
            
            # Update availability        
            if rerouted_start_station != "NA" and rerouted_end_station != "NA":
                # account for bike leaving rerouted start and arriving at rerouted destination
                availability[rerouted_start_station] -= 1 
                availability[rerouted_end_station] += 1

                print "\t".join(map(str,[row["starttime"], 
                    rerouted_start_station, 
                    availability[rerouted_start_station],
                    station_cap[rerouted_start_station],
                    station_prox[start_station][rerouted_start_station],
                    rerouted_end_station,
                    availability[rerouted_end_station],
                    station_cap[rerouted_end_station],
                    station_prox[end_station][rerouted_end_station]]))
            else:
                # print discarded trip for bookkeeping
                print "\t".join(map(str,[row["starttime"],
                                start_station,
                                availability[start_station],station_cap[start_station],"NA",
                                end_station,
                                availability[end_station],station_cap[end_station], "NA"]))
