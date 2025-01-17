#!/usr/bin/env python3
# grade_ex2.py

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
    'archive_format': 10,        # -10 if not .tgz or .zip
    'filename_correct': 10,      # -10 if filenames incorrect
    'readme_txt_extension': 3,   # -3 if README has .txt extension
    'comments_missing': 5,       # -5 if no comments in first 10 lines of both files
}
TOTAL_POINTS = 100

# Initialize Logging
def setup_logging():
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_filename = os.path.join(LOGS_DIR, f'grading_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
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
    expected_files = ['ex2a.c', 'ex2b.c']
    found_files = os.listdir(submission_path)
    filenames_correct = all(file in found_files for file in expected_files)
    incorrect_filenames = [file for file in found_files if file not in expected_files and file.endswith('.c')]
    if not filenames_correct and incorrect_filenames:
        logging.warning(f"Incorrect filenames found: {incorrect_filenames}")
        return False, incorrect_filenames
    return True, []

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

# Run Program A
def run_program_a(submission_path, executable_name, queue):
    """
    Runs Program A (ex2a) by sending inputs programmatically.
    Captures the output and returns it via a queue.
    """
    try:
        executable_path = os.path.join(submission_path, executable_name)
        # Run the program with unbuffered output
        proc = subprocess.Popen(
            ["stdbuf", "-o0", executable_path],
            cwd=submission_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        outputs = []
        for iteration in range(10):
            # Wait for the prompt
            prompt = proc.stdout.readline()
            if not prompt:
                outputs.append(f"Program A Iteration {iteration+1}: No prompt received.")
                break
            outputs.append(f"Program A Iteration {iteration+1}: {prompt.strip()}")

            # Send '\n' to press enter
            proc.stdin.write('\n')
            proc.stdin.flush()
            outputs.append(f"Program A Iteration {iteration+1}: Sent enter.")

            # Wait a bit to allow the program to set alarm and start input
            time.sleep(1)  # Adjust as needed

            # Send "1 2 3\n" as inputs
            inputs = "1 2 3\n"
            proc.stdin.write(inputs)
            proc.stdin.flush()
            outputs.append(f"Program A Iteration {iteration+1}: Sent inputs: {inputs.strip()}")

            # Do not send SIGALRM; let the program handle it

        # After all iterations, close stdin and wait for program to finish
        proc.stdin.close()
        try:
            proc.wait(timeout=TIMEOUT_EXECUTION + 10)
            if proc.returncode != 0:
                outputs.append(f"Program A exited with return code {proc.returncode}")
        except subprocess.TimeoutExpired:
            proc.kill()
            outputs.append("Program A did not terminate as expected.")
            queue.put("Execution timed out.")
            return

        # Capture the final output
        final_output = proc.stdout.read().strip()
        if final_output:
            outputs.append(f"Program A Final Output: {final_output}")

        # Capture any remaining stderr output
        remaining_stderr = proc.stderr.read().strip()
        if remaining_stderr:
            outputs.append(f"Program A Remaining Stderr: {remaining_stderr}")

        # Send all collected outputs to the main process
        captured_output = "\n".join(outputs)
        queue.put(captured_output)
    except Exception as e:
        logging.error(f"Error running Program A: {e}", exc_info=True)
        queue.put(f"Execution Error: {e}")

# Run Program B
def run_program_b(submission_path, executable_name, queue):
    """
    Runs Program B (ex2b) by executing it directly.
    Captures stdout and stderr, saves them to a file, and reads the output.
    Returns the captured output via a queue.
    """
    try:
        executable_path = os.path.join(submission_path, executable_name)
        output_file = os.path.join(submission_path, 'ex2b_output.txt')
        
        # Ensure the executable has execute permissions
        os.chmod(executable_path, 0o755)
        
        # Run the executable, redirecting stdout and stderr to the output file
        with open(output_file, 'w') as f:
            proc = subprocess.run(
                [executable_path],
                cwd=submission_path,
                stdin=subprocess.DEVNULL,    # No input required
                stdout=f,
                stderr=f,
                universal_newlines=True,
                timeout=120                    # Adjust timeout as needed
            )
        
        # Read the captured output from the file
        with open(output_file, 'r') as f:
            output = f.read()
        
        # Capture the exit code
        exit_code = proc.returncode
        
        # Prepare the captured output message
        captured_output = f"Program B Output:\n{output.strip()}\nProgram B Exit Code: {exit_code}"
        queue.put(captured_output)
        
        # Optional: Remove the output file after reading
        try:
            os.remove(output_file)
        except OSError as e:
            logging.warning(f"Failed to remove output file {output_file}: {e}")
        
    except subprocess.TimeoutExpired:
        logging.error("Program B execution timed out.")
        queue.put("Execution Timeout")
    except Exception as e:
        logging.error(f"Error running Program B: {e}", exc_info=True)
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
            "ex2a.c": True,
            "ex2b.c": True
        },
        "Compilation Warnings": {
            "ex2a.c": [],
            "ex2b.c": []
        },
        "Compilation Errors": {
            "ex2a.c": [],
            "ex2b.c": []
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
            "ex2a.c": True,
            "ex2b.c": True
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

    # Verify and Compile ex2a.c
    source_a = 'ex2a.c'
    executable_a = 'ex2a'
    if os.path.exists(os.path.join(submission_path, source_a)):
        success_a, compile_msg_a = compile_program(submission_path, source_a, executable_a)
        if not success_a:
            log_entry["Compilation"][source_a] = False
            log_entry["Compilation Errors"][source_a].append(compile_msg_a)
            log_entry["Issues"].append(f"Compilation failed for {source_a}.")
            deductions += 10  # Arbitrary deduction for compilation failure
            log_entry["Points Deducted"] += 10
    else:
        log_entry["Compilation"][source_a] = False
        log_entry["Compilation Errors"][source_a].append("File not found.")
        log_entry["Issues"].append(f"{source_a} not found.")
        deductions += 10
        log_entry["Points Deducted"] += 10

    # Verify and Compile ex2b.c
    source_b = 'ex2b.c'
    executable_b = 'ex2b'
    if os.path.exists(os.path.join(submission_path, source_b)):
        success_b, compile_msg_b = compile_program(submission_path, source_b, executable_b)
        if not success_b:
            log_entry["Compilation"][source_b] = False
            log_entry["Compilation Errors"][source_b].append(compile_msg_b)
            log_entry["Issues"].append(f"Compilation failed for {source_b}.")
            deductions += 10
            log_entry["Points Deducted"] += 10
    else:
        log_entry["Compilation"][source_b] = False
        log_entry["Compilation Errors"][source_b].append("File not found.")
        log_entry["Issues"].append(f"{source_b} not found.")
        deductions += 10
        log_entry["Points Deducted"] += 10

    # Check comments in ex2a.c and ex2b.c
    comments_a, lines_a = True, []
    comments_b, lines_b = True, []
    if os.path.exists(os.path.join(submission_path, source_a)):
        comments_a, lines_a = check_comments(submission_path, source_a)
        log_entry["Comments Present"]["ex2a.c"] = comments_a
    if os.path.exists(os.path.join(submission_path, source_b)):
        comments_b, lines_b = check_comments(submission_path, source_b)
        log_entry["Comments Present"]["ex2b.c"] = comments_b
    if not (comments_a or comments_b):
        log_entry["Issues"].append("No comments found in the first 10 lines of both ex2a.c and ex2b.c.")
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

    # Run Program A if compiled successfully
    if log_entry["Compilation"].get(source_a, False):
        queue_a = Queue()
        proc_a = Process(target=run_program_a, args=(submission_path, executable_a, queue_a))
        proc_a.start()
        proc_a.join(timeout=TIMEOUT_EXECUTION + 10)  # Increased timeout to accommodate 10 iterations
        if proc_a.is_alive():
            proc_a.terminate()
            log_entry["Execution Errors"]["Program A"] = "Execution timed out."
            deductions += 5
            log_entry["Points Deducted"] += 5
            queue_a.put("Execution timed out.")
        try:
            output_a = queue_a.get_nowait()
        except:
            output_a = "No Output"
        log_entry["Output Capturing"]["Program A"] = output_a
        logging.info(f"Program A Output:\n{output_a}")
    else:
        log_entry["Execution Errors"]["Program A"] = "Compilation failed."

    # Run Program B if compiled successfully
    if log_entry["Compilation"].get(source_b, False):
        queue_b = Queue()
        proc_b = Process(target=run_program_b, args=(submission_path, executable_b, queue_b))
        proc_b.start()
        proc_b.join(timeout=130)  # Align with run_program_b's 120 seconds timeout + buffer
        if proc_b.is_alive():
            proc_b.terminate()
            log_entry["Execution Errors"]["Program B"] = "Execution timed out."
            deductions += 5
            log_entry["Points Deducted"] += 5
            queue_b.put("Execution timed out.")
        try:
            output_b = queue_b.get_nowait()
        except:
            output_b = "No Output"
        log_entry["Output Capturing"]["Program B"] = output_b
        logging.info(f"Program B Output:\n{output_b}")
    else:
        log_entry["Execution Errors"]["Program B"] = "Compilation failed."

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
    logging.info("Starting grading process for Exercise 2 (ex2).")

    # Ensure necessary directories exist
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs('workdir', exist_ok=True)  # If needed

    summary_file = os.path.join(SUMMARY_DIR, 'summary_ex2.json')

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

    logging.info("Grading complete for Exercise 2 (ex2).")

if __name__ == "__main__":
    main()
