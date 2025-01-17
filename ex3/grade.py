#!/usr/bin/env python3
# grade_ex3.py

import os
import tarfile
import subprocess
import shutil
import json
import re
import logging
import time
from datetime import datetime
from multiprocessing import Process, Queue

# Configuration Constants
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SUBMISSIONS_DIR = os.path.join(SCRIPT_DIR, 'submissions')
SUMMARY_DIR = os.path.join(SCRIPT_DIR, 'summary')
LOGS_DIR = os.path.join(SCRIPT_DIR, 'logs')

GCC_COMMAND = 'gcc'
TIMEOUT_EXECUTION = 60  # seconds for program execution
POINTS = {
    'archive_format': 10,          # -10 if not .tgz or .zip
    'filename_correct': 10,        # -10 if filenames incorrect
    'readme_txt_extension': 2,     # -2 if README has .txt extension
    'comments_missing': 5,         # -5 if no comments in first 10 lines of both files
    'extra_c_files': 2,            # -2 per extra .c file
}
TOTAL_POINTS = 100

SEED_A = "12345"  # Example seed for ex3a
SEED_B = "67890"  # Example seed for ex3b

# Initialize Logging
def setup_logging():
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_filename = os.path.join(LOGS_DIR, f'grading_ex3_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    # Create a custom logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Create handlers
    file_handler = logging.FileHandler(log_filename)
    console_handler = logging.StreamHandler()
    
    # Set levels for handlers
    file_handler.setLevel(logging.INFO)
    console_handler.setLevel(logging.INFO)
    
    # Create formatters and add them to handlers
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    # Add handlers to the logger
    if not logger.hasHandlers():
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

# Extract Submission
def extract_submission(archive_path, extract_path):
    try:
        if archive_path.endswith(('.tgz', '.tar.gz')):
            with tarfile.open(archive_path, 'r:gz') as tar_ref:
                tar_ref.extractall(extract_path)
            archive_type = "TGZ"
        elif archive_path.endswith('.zip'):
            import zipfile
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            archive_type = "ZIP"
        else:
            raise ValueError("Unsupported archive format.")
        
        extracted_files = os.listdir(extract_path)
        logging.info(f"Extracted files: {extracted_files}")
        return True, archive_type
    except Exception as e:
        logging.error(f"Failed to extract {archive_path}: {e}", exc_info=True)
        return False, str(e)

# Verify Filenames
def verify_filenames(submission_path):
    expected_files = ['ex3a.c', 'ex3b.c']
    found_files = os.listdir(submission_path)
    c_files = [file for file in found_files if file.endswith('.c')]
    
    filenames_correct = all(file in found_files for file in expected_files)
    incorrect_filenames = [file for file in c_files if file not in expected_files]
    
    return filenames_correct, incorrect_filenames

# Check README Extension
def check_readme_extension(submission_path):
    readme_files = [f for f in os.listdir(submission_path) if re.match(r'^readme(\.txt)?$', f, re.IGNORECASE)]
    if not readme_files:
        logging.warning("README file not found.")
        return False, None
    readme_file = readme_files[0]
    has_txt_extension = readme_file.lower().endswith('.txt')
    if has_txt_extension:
        logging.warning("README file has .txt extension.")
    return has_txt_extension, readme_file

# Compile Program
def compile_program(submission_path, source_file, output_executable):
    source_path = os.path.join(submission_path, source_file)
    output_path = os.path.join(submission_path, output_executable)
    compile_cmd = [GCC_COMMAND, '-Wall', '-o', output_executable, source_file]
    try:
        result = subprocess.run(
            compile_cmd,
            cwd=submission_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=TIMEOUT_EXECUTION
        )
        compile_stdout = result.stdout.strip()
        compile_stderr = result.stderr.strip()
        if result.returncode != 0:
            logging.error(f"Compilation failed for {source_file}: {compile_stderr}")
            return False, compile_stderr
        else:
            if compile_stderr:
                logging.warning(f"Compilation warnings for {source_file}: {compile_stderr}")
            else:
                logging.info(f"Compilation succeeded for {source_file} with no warnings.")
            return True, compile_stderr
    except subprocess.TimeoutExpired:
        logging.error(f"Compilation timed out for {source_file}.")
        return False, "Compilation timed out."
    except Exception as e:
        logging.error(f"Compilation error for {source_file}: {e}", exc_info=True)
        return False, str(e)

# Check Comments in First 10 Lines
def check_comments(submission_path, source_file):
    source_path = os.path.join(submission_path, source_file)
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            lines = [f.readline().strip() for _ in range(10)]
        comments_present = any(re.match(r'^\s*(//|/\*)', line) for line in lines if line)
        if comments_present:
            logging.info(f"Comments found in {source_file}.")
        else:
            logging.warning(f"No comments found in the first 10 lines of {source_file}.")
        return comments_present, lines
    except Exception as e:
        logging.error(f"Failed to read {source_file}: {e}", exc_info=True)
        return False, []

# Extract README First 10 Lines
def extract_readme(submission_path, readme_file):
    readme_path = os.path.join(submission_path, readme_file)
    try:
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme_lines = [f.readline().strip() for _ in range(10)]
        logging.info(f"Extracted first 10 lines of README from {readme_file}.")
        return readme_lines
    except Exception as e:
        logging.error(f"Failed to read README file {readme_file}: {e}", exc_info=True)
        return []

# Generic Run Program Function
def run_program(submission_path, executable_name, seed, output_filename, queue):
    """
    Runs a program by executing it with a seed argument.
    Redirects stdout and stderr to an output file.
    Reads the output file and sends the content via a queue.
    """
    try:
        executable_path = os.path.join(submission_path, executable_name)
        output_file = os.path.join(submission_path, output_filename)
        
        # Ensure the executable has execute permissions
        os.chmod(executable_path, 0o755)
        logging.info(f"Running {executable_name} with seed {seed}.")
        logging.info(f"program path: {executable_path}")
        # Run the executable, redirecting stdout and stderr to the output file
        with open(output_file, 'w') as f:
            proc = subprocess.run(
                [executable_path, str(seed)],
                cwd=submission_path,
                stdin=subprocess.DEVNULL,    # No input required
                stdout=f,
                stderr=f,
                universal_newlines=True,
                timeout=TIMEOUT_EXECUTION
            )
        
        # Read the captured output from the file
        with open(output_file, 'r') as f:
            output = f.read()
        
        # Capture the exit code
        exit_code = proc.returncode
        
        # Prepare the captured output message
        captured_output = f"{executable_name} Output:\n{output.strip()}\n{executable_name} Exit Code: {exit_code}"
        queue.put(captured_output)
        
        # Remove the output file after reading
        try:
            os.remove(output_file)
        except OSError as e:
            logging.warning(f"Failed to remove output file {output_file}: {e}")
        
    except subprocess.TimeoutExpired:
        logging.error(f"{executable_name} execution timed out.")
        queue.put("Execution Timeout")
    except Exception as e:
        logging.error(f"Error running {executable_name}: {e}", exc_info=True)
        queue.put(f"Execution Error: {e}")

# Process Single Submission
def process_submission(submission_folder):
    log_entry = {
        "Student ID": "",
        "Student Name": "",
        "Submission Folder": submission_folder,
        "Archive Type": "",
        "Filename Correct": True,
        "Readme Txt Extension": False,
        "Content Structure": True,
        "Compilation": {
            "ex3a.c": True,
            "ex3b.c": True
        },
        "Compilation Warnings": {
            "ex3a.c": [],
            "ex3b.c": []
        },
        "Compilation Errors": {
            "ex3a.c": [],
            "ex3b.c": []
        },
        "Execution Errors": {
            "Program A": "",
            "Program B": ""
        },
        "Output Capturing": {
            "Program A": "",
            "Program B": ""
        },
        "Comments Present": {
            "ex3a.c": True,
            "ex3b.c": True
        },
        "README First 10 Lines": [],
        "Issues": [],
        "Points Deducted": 0,
        "Final Score": TOTAL_POINTS
    }

    deductions = 0

    submission_path = os.path.join(SUBMISSIONS_DIR, submission_folder)

    # Extract Student ID and Name from folder name
    match = re.match(r'^(.*?)_(\d+)_assignsubmission_file$', submission_folder)
    if match:
        student_name = match.group(1).strip()
        student_id = match.group(2).strip()
        log_entry["Student ID"] = student_id
        log_entry["Student Name"] = student_name
    else:
        logging.warning(f"Folder name '{submission_folder}' does not match the expected pattern.")
        log_entry["Student ID"] = "Unknown_ID"
        log_entry["Student Name"] = "Unknown_Name"
        log_entry["Issues"].append("Folder name does not match the expected pattern.")
        deductions += 5  # Arbitrary deduction for naming issues

    # Find the archive file
    archive_files = [f for f in os.listdir(submission_path) if f.endswith(('.tgz', '.tar.gz', '.zip'))]
    non_supported_archives = [f for f in os.listdir(submission_path) if not f.endswith(('.tgz', '.tar.gz', '.zip')) and f.endswith('.rar')]

    if not archive_files and non_supported_archives:
        # Non-supported archive found
        logging.info(f"Non-supported archive found: {non_supported_archives[0]}")
        archive_file = non_supported_archives[0]
        success, archive_type = extract_submission(os.path.join(submission_path, archive_file), submission_path)
        if success:
            log_entry["Archive Type"] = archive_type
            log_entry["Issues"].append("Non-supported archive submitted.")
            deductions += POINTS['archive_format']
            log_entry["Points Deducted"] += POINTS['archive_format']
        else:
            log_entry["Archive Type"] = "Unknown"
            log_entry["Issues"].append("Failed to extract non-supported archive.")
            deductions += POINTS['archive_format']
            log_entry["Points Deducted"] += POINTS['archive_format']
            return log_entry  # Cannot proceed without extraction
    elif archive_files:
        # Supported archive found
        archive_file = archive_files[0]
        success, archive_type = extract_submission(os.path.join(submission_path, archive_file), submission_path)
        if success:
            log_entry["Archive Type"] = archive_type
            # Check if the archive format is not .tgz or .zip and deduct points
            if archive_type not in ["TGZ", "ZIP"]:
                log_entry["Issues"].append(f"Unsupported archive format: {archive_type}.")
                deductions += POINTS['archive_format']
                log_entry["Points Deducted"] += POINTS['archive_format']
        else:
            log_entry["Archive Type"] = "Unknown"
            log_entry["Issues"].append("Failed to extract supported archive.")
            deductions += POINTS['archive_format']
            log_entry["Points Deducted"] += POINTS['archive_format']
            return log_entry  # Cannot proceed without extraction
    else:
        # No archive found
        logging.error(f"No supported archive file found in {submission_folder}.")
        log_entry["Issues"].append("No supported archive file found.")
        deductions += POINTS['archive_format']
        log_entry["Points Deducted"] += POINTS['archive_format']
        return log_entry  # Cannot proceed without archive

    # Verify filenames
    filenames_correct, incorrect_filenames = verify_filenames(submission_path)
    if not filenames_correct:
        log_entry["Filename Correct"] = False
        log_entry["Issues"].append(f"Incorrect filenames: {incorrect_filenames}")
        deductions += POINTS['filename_correct']
        log_entry["Points Deducted"] += POINTS['filename_correct']

    # Check README extension
    has_txt_ext, readme_file = check_readme_extension(submission_path)
    log_entry["Readme Txt Extension"] = has_txt_ext
    if has_txt_ext:
        log_entry["Issues"].append("README file has .txt extension.")
        deductions += POINTS['readme_txt_extension']
        log_entry["Points Deducted"] += POINTS['readme_txt_extension']

    # Verify and Compile ex3a.c and ex3b.c
    source_a = 'ex3a.c'
    executable_a = 'ex3a'
    source_b = 'ex3b.c'
    executable_b = 'ex3b'

    # Dictionary to hold mapping of source files to executables
    sources = {
        source_a: executable_a,
        source_b: executable_b
    }

    # Track which sources have incorrect filenames
    incorrect_sources = []

    for source_file, executable in sources.items():
        source_path = os.path.join(submission_path, source_file)
        if os.path.exists(source_path):
            success, compile_msg = compile_program(submission_path, source_file, executable)
            if not success:
                log_entry["Compilation"][source_file] = False
                log_entry["Compilation Errors"][source_file].append(compile_msg)
                log_entry["Issues"].append(f"Compilation failed for {source_file}.")
                deductions += 10  # Arbitrary deduction for compilation failure
                log_entry["Points Deducted"] += 10
        else:
            # If the expected source file is missing, check for other .c files
            c_files = [f for f in os.listdir(submission_path) if f.endswith('.c')]
            if len(c_files) >= 2:
                # Assume the missing file is replaced by another .c file
                for f in c_files:
                    if f not in sources:
                        incorrect_sources.append(f)
                        # Attempt to compile and run the incorrectly named file
                        incorrect_executable = f.replace('.c', '')
                        success, compile_msg = compile_program(submission_path, f, incorrect_executable)
                        if not success:
                            log_entry["Compilation"][f] = False
                            log_entry["Compilation Errors"][f].append(compile_msg)
                            log_entry["Issues"].append(f"Compilation failed for {f} (expected {source_file}).")
                            deductions += 10
                            log_entry["Points Deducted"] += 10
                if incorrect_sources:
                    log_entry["Issues"].append(f"Incorrect filenames: {incorrect_sources}")
                    deductions += POINTS['filename_correct']
                    log_entry["Points Deducted"] += POINTS['filename_correct']
            elif len(c_files) > 2:
                # More than two .c files found
                extra_c_files = [f for f in c_files if f not in sources]
                log_entry["Issues"].append(f"Extra .c files found: {extra_c_files}")
                deductions += len(extra_c_files) * POINTS['extra_c_files']  # Deduct per extra file
                log_entry["Points Deducted"] += len(extra_c_files) * POINTS['extra_c_files']
                # Attempt to compile all .c files
                for f in extra_c_files:
                    incorrect_sources.append(f)
                    incorrect_executable = f.replace('.c', '')
                    success, compile_msg = compile_program(submission_path, f, incorrect_executable)
                    if not success:
                        log_entry["Compilation"][f] = False
                        log_entry["Compilation Errors"][f].append(compile_msg)
                        log_entry["Issues"].append(f"Compilation failed for {f} (expected {source_file}).")
                        deductions += 10
                        log_entry["Points Deducted"] += 10
            else:
                # Less than two .c files found
                log_entry["Compilation"][source_file] = False
                log_entry["Compilation Errors"][source_file].append("File not found.")
                log_entry["Issues"].append(f"{source_file} not found.")
                deductions += 10
                log_entry["Points Deducted"] += 10

    # Check comments in ex3a.c and ex3b.c (or incorrectly named files)
    for source_file, executable in sources.items():
        source_path = os.path.join(submission_path, source_file)
        if os.path.exists(source_path):
            comments_present, lines = check_comments(submission_path, source_file)
            log_entry["Comments Present"][source_file] = comments_present
        else:
            # Check if an incorrectly named .c file was compiled
            c_files = [f for f in os.listdir(submission_path) if f.endswith('.c')]
            for f in c_files:
                if f not in sources:
                    comments_present, lines = check_comments(submission_path, f)
                    log_entry["Comments Present"][f] = comments_present
                    if comments_present:
                        log_entry["Comments Present"][source_file] = True  # Assume comments are present for expected file
                    else:
                        log_entry["Comments Present"][source_file] = False

    # Determine if comments are missing in both ex3a.c and ex3b.c (or their incorrect counterparts)
    comments_a_present = log_entry["Comments Present"].get(source_a, False)
    comments_b_present = log_entry["Comments Present"].get(source_b, False)

    if not (comments_a_present or comments_b_present):
        log_entry["Issues"].append("No comments found in the first 10 lines of both ex3a.c and ex3b.c.")
        deductions += POINTS['comments_missing']
        log_entry["Points Deducted"] += POINTS['comments_missing']

    # Extract README first 10 lines
    if readme_file:
        readme_lines = extract_readme(submission_path, readme_file)
        log_entry["README First 10 Lines"] = readme_lines
    else:
        log_entry["README First 10 Lines"] = []
        log_entry["Issues"].append("README file missing.")
        deductions += POINTS['readme_txt_extension']
        log_entry["Points Deducted"] += POINTS['readme_txt_extension']

    # Run Programs A and B if compiled successfully
    programs = {
        "Program A": {
            "executable": "ex3a",
            "seed": SEED_A,
            "output_file": "ex3a_output.txt"
        },
        "Program B": {
            "executable": "ex3b",
            "seed": SEED_B,
            "output_file": "ex3b_output.txt"
        }
    }

    for program_label, program_info in programs.items():
        executable = program_info["executable"]
        seed = program_info["seed"]
        output_file = program_info["output_file"]

        executable_path = os.path.join(submission_path, executable)
        if os.path.exists(executable_path):
            queue = Queue()
            proc = Process(target=run_program, args=(submission_path, executable, seed, output_file, queue))
            proc.start()
            proc.join(timeout=TIMEOUT_EXECUTION + 10)  # Increased timeout to accommodate execution
            if proc.is_alive():
                proc.terminate()
                log_entry["Execution Errors"][program_label] = "Execution timed out."
                deductions += 5
                log_entry["Points Deducted"] += 5
                queue.put("Execution timed out.")
            try:
                output = queue.get_nowait()
            except:
                output = "No Output"
            log_entry["Output Capturing"][program_label] = output
            logging.info(f"{program_label} Output:\n{output}")
        else:
            log_entry["Execution Errors"][program_label] = "Compilation failed or executable not found."

    # Finalize scoring
    log_entry["Points Deducted"] = deductions
    log_entry["Final Score"] = max(TOTAL_POINTS - deductions, 0)

    return log_entry

# Generate JSON Summary
def generate_json_summary(summary, output_path):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=4, ensure_ascii=False)
        logging.info(f"JSON summary generated at {output_path}")
    except Exception as e:
        logging.error(f"Failed to write JSON summary: {e}", exc_info=True)

# Main Function
def main():
    setup_logging()
    logging.info("Starting grading process for Exercise 3 (ex3).")

    # Ensure necessary directories exist
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs('workdir', exist_ok=True)  # If needed

    summary_file = os.path.join(SUMMARY_DIR, 'summary_ex3.json')

    # Initialize summary list
    summary = []

    # Iterate over each submission folder in submissions
    for submission_folder in os.listdir(SUBMISSIONS_DIR):
        submission_path = os.path.join(SUBMISSIONS_DIR, submission_folder)
        if not os.path.isdir(submission_path):
            logging.warning(f"Skipping non-directory item in submissions: {submission_folder}")
            continue  # Skip non-directory items

        logging.info(f"Processing submission folder: {submission_folder}")

        # Process the submission
        log = process_submission(submission_folder)
        summary.append(log)
        logging.info(f"Finished processing: {submission_folder} | Final Score: {log['Final Score']}")

    # Generate JSON Summary
    generate_json_summary(summary, summary_file)

    logging.info("Grading complete for Exercise 3 (ex3).")

if __name__ == "__main__":
    main()
