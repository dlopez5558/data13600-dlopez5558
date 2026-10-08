import random
import sys
import csv

filename = sys.argv[1]
x = 0

with open(filename, newline="") as file:
    reader = csv.reader(file)
    
    for row in reader:
        if random.random() < 0.01:
            print(row)
