import numpy as np


def extract_bpm_pattern(lengh: int, frame_rate: int) -> None:
    array = np.full((240, lengh, 32), 0, dtype=np.int64)
    jump = int(0)
    add = 0

    for i in range(240):
        add += 0.25
        timestamp = int(60 / (100 + add) * frame_rate)
        jump = int(0)
        for x in range(lengh):
            timestamp_next = 0
            jump += 20
            for y in range(32):
                array[i][x][y] = timestamp_next
                timestamp_next += timestamp
            array[i][x] = array[i][x] + jump  
            
    np.save("bpm_pattern.npy", array)


def extract_bpm_pattern_fine(lengh: int, frame_rate: int) -> None:
    array = np.full((1200, lengh, 32), 0, dtype=np.int64)
    jump = int(0)
    add = 0
    
    for i in range(1200):
        timestamp = int(60 / (100 + add) * frame_rate)
        add += 0.05
        jump = int(0)
        for x in range(lengh):
            timestamp_next = 0
            jump += 20
            for y in range(32):
                array[i][x][y] = timestamp_next
                timestamp_next += timestamp
            array[i][x] = array[i][x] + jump
            
    np.save("bpm_pattern_fine.npy", array)


def extract(frame_rate: int):
    print("PATTERN CREATOR")
    print("extracting...")
    lengh = int((frame_rate / 2) / 20)
    extract_bpm_pattern(lengh, frame_rate)
    extract_bpm_pattern_fine(lengh, frame_rate)
    print("\033[92m" + "COMPLETED" + "\033[0m")
    
