import os
import json
import torch
import logging
import traceback
from typing import List, Dict, Any

from .caching import cached_file, cached_file_object


@cached_file_object('.merged')
def merge_transcript_diarization(video_path: str, transcript: list, diarization: list):
    # Create a new list to store merged results
    merged = []

    # Sort both arrays by start time just to be safe
    transcript = sorted(transcript, key=lambda x: x["start"])
    diarization = sorted(diarization, key=lambda x: x["start"])

    # Keep track of current position in both arrays
    t_idx = 0  # transcript index
    d_idx = 0  # diarization index

    # Handle case where one or both arrays are empty
    if not transcript or not diarization:
        return transcript if transcript else []

    current_time = min(transcript[0]["start"], diarization[0]["start"])
    max_time = max(
        transcript[-1]["end"] if transcript else 0,
        diarization[-1]["end"] if diarization else 0
    )

    while current_time < max_time and (t_idx < len(transcript) or d_idx < len(diarization)):
        # Get current transcript and diarization segments if available
        curr_trans = transcript[t_idx] if t_idx < len(transcript) else None
        curr_diar = diarization[d_idx] if d_idx < len(diarization) else None

        # Determine the next end time
        next_end = float('inf')
        if curr_trans:
            next_end = min(next_end, curr_trans["end"])
        if curr_diar:
            next_end = min(next_end, curr_diar["end"])

        # If no transcript in this segment, create a silent segment
        if not curr_trans or (curr_diar and curr_diar["end"] < curr_trans["start"]):
            if curr_diar:
                merged.append({
                    "start": current_time,
                    "end": min(next_end, curr_diar["end"]),
                    "transcript": "[SILENCE]",
                    "speaker": curr_diar["speaker"],
                    "duration": min(next_end, curr_diar["end"]) - current_time
                })
            else:
                merged.append({
                    "start": current_time,
                    "end": next_end,
                    "transcript": "[SILENCE]",
                    "speaker": "UNKNOWN",
                    "duration": next_end - current_time
                })
        # If we have a transcript segment
        else:
            speaker = "UNKNOWN"
            # Find overlapping diarization segment
            if curr_diar and curr_diar["start"] <= curr_trans["end"] and curr_diar["end"] >= curr_trans["start"]:
                speaker = curr_diar["speaker"]

            merged.append({
                "start": current_time,
                "end": next_end,
                "transcript": curr_trans["transcript"],
                "speaker": speaker,
                "duration": next_end - current_time,
            })

        # Update indices and current_time
        current_time = next_end

        if curr_trans and next_end >= curr_trans["end"]:
            t_idx += 1
        if curr_diar and next_end >= curr_diar["end"]:
            d_idx += 1

    return merged

@cached_file_object('.compressed')
def compress_transcript(video_path: str, entries: list):
    ''' Compress repreated senstences '''
    if not entries:
        return []

    compressed = []
    current = dict(entries[0])  # Create a copy of the first entry
    duration = current["duration"]
    speaker = current["speaker"]

    for entry in entries[1:]:
        # Check if current entry matches the previous one in transcript and speaker
        if (entry['transcript'] == current['transcript'] and 
            entry['start'] == current['end']):  # Check if times are consecutive
            # Update the end time to the current entry's end time
            current['end'] = entry['end']
            if entry["duration"] > duration:
                # Select one ker corresponding to largest duration
                speaker = entry['speaker']
        else:
            # Add the completed entry to our result and start a new one
            compressed.append(current)
            current = dict(entry)  # Create a copy of the new entry
            duration = current['duration']
            speaker  =  current['speaker']
    # Don't forget to add the last entry
    compressed.append(current)

    return compressed

        


def speaker_to_name(introductions: str):
    # Initialize an empty dictionary for the result
    result = {}

    # Iterate over each entry in the list
    for item in introductions:
        speaker_key = item['speaker']
        speaker_value = item['speaker_name']

        # If the speaker is UNKNOWN, set the value to UNKNOWN
        if speaker_key == "UNKNOWN":
            speaker_value = "UNKNOWN"

        # Add the mapping to the result dictionary
        result[speaker_key] = speaker_value
    return result

@cached_file_object('.final')    
def map_speakers(video_path: str, transcripts: list, speaker_to_name: dict):
    return  [transcript | {'speaker_name': speaker_to_name.get(transcript['speaker'],transcript['speaker'])} for transcript in transcripts]

@cached_file('.formatted')
def format_transcript(video_path: str, transcripts: str) -> str:
    """Format final transcript as Markdown"""
    try:
        formatted = "# Transcribed Video\n\n"
        # This is a simplified formatting - enhance as needed
        for entry in transcripts:
            speaker = entry['speaker_name']
            transcript = entry['transcript']
            formatted += f"{speaker}:{transcript}\n"
        return formatted
    except Exception as e:
        print(f"Error formatting transcript: {e}")
        return transcript

@cached_file('.md')
def format_markdown(video_path: str, transcripts: List[Dict[str, Any]]) -> str:
    """Formats the final transcript as Markdown."""
    try:
        formatted = "# Transcribed Video\n\n"
        current_speaker = None
        for entry in transcripts:
            speaker = entry.get('speaker_name', 'UNKNOWN') # Use .get for safety
            transcript_text = entry.get('transcript', '[TRANSCRIPT MISSING]')

            # Add speaker heading only when the speaker changes
            if speaker != current_speaker:
                formatted += f"**{speaker}:**\n"
                current_speaker = speaker

            # Add the transcript text, indented slightly
            formatted += f"- {transcript_text}\n"
        return formatted
    except Exception as e:
        print(f"Error formatting transcript: {e}")
        # Attempt to return a basic representation even on error
        return json.dumps(transcripts, indent=2)

    
