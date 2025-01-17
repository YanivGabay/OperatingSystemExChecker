#!/usr/bin/env python3
# grade_ex4.py

import os
import tarfile
import subprocess
import json
import re
import logging
import time
from datetime import datetime
from multiprocessing import Process, Queue
import zipfile
import shutil
import signal

# Configuration Constants
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SUBMISSIONS_DIR = os.path.join(SCRIPT_DIR, 'submissions')
SUMMARY_DIR = os.path.join(SCRIPT_DIR, 'summary')
LOGS_DIR = os.path.join(SCRIPT_DIR, 'logs')
# We extract files directly into the submission folder so that they remain available.
WORKDIR = SUBMISSIONS_DIR  

GCC_COMMAND = 'gcc'
TIMEOUT_EXECUTION = 60  # seconds for program execution
POINTS = {
    'archive_format': 10,          # Deduct if archive is not .tgz/.tar.gz or .zip
    'filename_correct': 10,        # Deduct if expected filenames are not exactly present
    'readme_txt_extension': 2,     # Deduct if README uses .txt extension
    'comments_missing': 5,         # Deduct if no comments in first 10 lines in a file
    'extra_c_files': 2,            # Deduct per extra .c file
}
TOTAL_POINTS = 100

# Example seeds (if needed)
SEED_A = "12345"  # For ex4a* programs
SEED_B = "67890"  # For ex4b* programs

### Logging Setup ###
def setup_logging():
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_filename = os.path.join(LOGS_DIR, f'grading_ex4_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(log_filename)
    console_handler = logging.StreamHandler()
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    if not logger.hasHandlers():
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

### Archive Extraction ###
def extract_archive(archive_path, extract_to):
    try:
        if archive_path.endswith(('.tgz', '.tar.gz')):
            with tarfile.open(archive_path, 'r:gz') as tar_ref:
                tar_ref.extractall(extract_to)
            archive_type = "TGZ"
        elif archive_path.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            archive_type = "ZIP"
        else:
            archive_type = "Unsupported"
            raise ValueError("Unsupported archive format.")
        files = os.listdir(extract_to)
        logging.info(f"Extracted files: {files}")
        return True, archive_type
    except Exception as e:
        logging.error(f"Failed to extract {archive_path}: {e}", exc_info=True)
        return False, str(e)

### Filename Verification ###
def verify_files(submission_path):
    expected = {
        'ex4a1.c': 'ex4a1',
        'ex4a2.c': 'ex4a2',
        'ex4b1.c': 'ex4b1',
        'ex4b2.c': 'ex4b2',
        'ex4c1.c': 'ex4c1',
        'ex4c2.c': 'ex4c2',
        'ex4c3.c': 'ex4c3'
    }
    found_files = os.listdir(submission_path)
    c_files = [f for f in found_files if f.endswith('.c')]
    missing = []
    wrong = []
    for exp in expected:
        if exp not in found_files:
            alternatives = [f for f in c_files if f.lower().replace(" ", "") == exp.lower().replace(" ", "")]
            if not alternatives:
                missing.append(exp)
            else:
                wrong.append(alternatives[0])
    return missing, wrong

### Check README Extension & Extract First 10 Lines ###
def check_readme_extension(submission_path):
    readme_files = [f for f in os.listdir(submission_path) if re.match(r'^readme(\.txt)?$', f, re.IGNORECASE)]
    if not readme_files:
        logging.warning("README file not found.")
        return False, None
    readme_file = readme_files[0]
    has_txt = readme_file.lower().endswith('.txt')
    if has_txt:
        logging.warning("README file has .txt extension.")
    return has_txt, readme_file

def extract_readme(submission_path, readme_file):
    readme_path = os.path.join(submission_path, readme_file)
    try:
        with open(readme_path, 'r', encoding='utf-8') as f:
            lines = [f.readline().strip() for _ in range(10)]
        logging.info(f"Extracted first 10 lines of README from {readme_file}.")
        return lines
    except Exception as e:
        logging.error(f"Failed to read README file {readme_file}: {e}", exc_info=True)
        return []

### Compilation ###
def compile_source(submission_path, source_file, output_executable):
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
        if result.returncode != 0:
            logging.error(f"Compilation failed for {source_file}: {result.stderr.strip()}")
            return False, result.stderr.strip()
        else:
            if result.stderr.strip():
                logging.warning(f"Compilation warnings for {source_file}: {result.stderr.strip()}")
            else:
                logging.info(f"Compilation succeeded for {source_file} with no warnings.")
            return True, result.stderr.strip()
    except subprocess.TimeoutExpired:
        logging.error(f"Compilation timed out for {source_file}.")
        return False, "Compilation timed out."
    except Exception as e:
        logging.error(f"Compilation error for {source_file}: {e}", exc_info=True)
        return False, str(e)

### Generic Run Program Function ###
def run_program(submission_path, executable, arg_list, output_filename, queue):
    """
    Runs a program with a list of arguments using unbuffered output.
    Output is redirected to a file which is then read and returned via the queue.
    """
    try:
        executable_path = os.path.join(submission_path, executable)
        output_file = os.path.join(submission_path, output_filename)
        os.chmod(executable_path, 0o755)
        # Build command with stdbuf for unbuffered output.
        cmd = ["stdbuf", "-o0", f"./{executable}"] + [str(arg) for arg in arg_list]
        logging.info(f"Running command: {' '.join(cmd)} in {submission_path}")
        with open(output_file, 'w') as out_f:
            proc = subprocess.run(
                cmd,
                cwd=submission_path,
                stdin=subprocess.DEVNULL,
                stdout=out_f,
                stderr=out_f,
                universal_newlines=True,
                timeout=TIMEOUT_EXECUTION
            )
        with open(output_file, 'r') as out_f:
            captured = out_f.read()
        exit_code = proc.returncode
        message = f"{executable} Output:\n{captured.strip()}\nExit Code: {exit_code}"
        queue.put(message)
        try:
            os.remove(output_file)
        except Exception as e:
            logging.warning(f"Could not remove output file {output_file}: {e}")
    except subprocess.TimeoutExpired:
        logging.error(f"{executable} execution timed out.")
        queue.put("Execution Timeout")
    except Exception as e:
        logging.error(f"Error running {executable}: {e}", exc_info=True)
        queue.put(f"Execution Error: {e}")

### Comments Checker ###
def check_comments(submission_path, source_file):
    source_path = os.path.join(submission_path, source_file)
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            lines = [f.readline().strip() for _ in range(10)]
        comments_present = any(line.startswith("//") or "/*" in line for line in lines if line)
        return comments_present, lines
    except Exception as e:
        logging.error(f"Failed to read {source_file}: {e}", exc_info=True)
        return False, []

### Process a Single Submission ###
def process_submission(submission_folder):
    log_entry = {
        "Student ID": "",
        "Student Name": "",
        "Submission Folder": submission_folder,
        "Archive Type": "",
        "Missing Files": [],
        "Wrong Filenames": [],
        "Compilation": {},
        "Compilation Warnings": {},
        "Compilation Errors": {},
        "Execution Outputs": {},
        "Comments Present": {},
        "README First 10 Lines": [],
        "Issues": [],
        "Points Deducted": 0,
        "Final Score": TOTAL_POINTS
    }
    deductions = 0
    submission_path = os.path.join(SUBMISSIONS_DIR, submission_folder)
    
    # Extract student info
    match = re.match(r'^(.*?)_(\d+)_assignsubmission_file$', submission_folder)
    if match:
        log_entry["Student Name"] = match.group(1).strip()
        log_entry["Student ID"] = match.group(2).strip()
    else:
        log_entry["Issues"].append("Folder name does not match expected pattern.")
        deductions += 5
    
    # Extract archive
    archives = [f for f in os.listdir(submission_path) if f.endswith(('.tgz', '.tar.gz', '.zip'))]
    if not archives:
        log_entry["Issues"].append("No supported archive found.")
        deductions += POINTS['archive_format']
        log_entry["Points Deducted"] += POINTS['archive_format']
        return log_entry
    archive_file = os.path.join(submission_path, archives[0])
    success, arch_type = extract_archive(archive_file, submission_path)
    if success:
        log_entry["Archive Type"] = arch_type
        if arch_type not in ["TGZ", "ZIP"]:
            log_entry["Issues"].append(f"Unsupported archive format: {arch_type}.")
            deductions += POINTS['archive_format']
            log_entry["Points Deducted"] += POINTS['archive_format']
    else:
        log_entry["Issues"].append("Failed to extract archive.")
        deductions += POINTS['archive_format']
        log_entry["Points Deducted"] += POINTS['archive_format']
        return log_entry

    # Verify files
    missing_files, wrong_files = verify_files(submission_path)
    if missing_files:
        log_entry["Missing Files"] = missing_files
        deductions += 10 * len(missing_files)
        log_entry["Points Deducted"] += 10 * len(missing_files)
    if wrong_files:
        log_entry["Wrong Filenames"] = wrong_files
        deductions += 10 * len(wrong_files)
        log_entry["Points Deducted"] += 10 * len(wrong_files)
    
    # Process README
    has_txt, readme_filename = check_readme_extension(submission_path)
    if not readme_filename:
        log_entry["Issues"].append("README file missing.")
        deductions += POINTS['readme_txt_extension']
        log_entry["Points Deducted"] += POINTS['readme_txt_extension']
    else:
        if has_txt:
            log_entry["Issues"].append("README file has .txt extension.")
            deductions += POINTS['readme_txt_extension']
            log_entry["Points Deducted"] += POINTS['readme_txt_extension']
        log_entry["README First 10 Lines"] = extract_readme(submission_path, readme_filename)
    
    # Compile expected source files
    expected_sources = {
        "ex4a1.c": "ex4a1",
        "ex4a2.c": "ex4a2",
        "ex4b1.c": "ex4b1",
        "ex4b2.c": "ex4b2",
        "ex4c1.c": "ex4c1",
        "ex4c2.c": "ex4c2",
        "ex4c3.c": "ex4c3"
    }
    for src, exe in expected_sources.items():
        src_path = os.path.join(submission_path, src)
        if os.path.exists(src_path):
            comp_ok, comp_msg = compile_source(submission_path, src, exe)
            log_entry["Compilation"][src] = comp_ok
            log_entry["Compilation Warnings"][src] = comp_msg
            if not comp_ok:
                log_entry["Compilation Errors"][src] = comp_msg
                log_entry["Issues"].append(f"Compilation failed for {src}.")
                deductions += 10
                log_entry["Points Deducted"] += 10
        else:
            log_entry["Compilation"][src] = False
            log_entry["Compilation Errors"][src] = "File not found."
            log_entry["Issues"].append(f"{src} not found.")
            deductions += 10
            log_entry["Points Deducted"] += 10
    
    # Check for comments in source files
    for src in expected_sources:
        src_path = os.path.join(submission_path, src)
        if os.path.exists(src_path):
            comments, _ = check_comments(submission_path, src)
            log_entry["Comments Present"][src] = comments
        else:
            log_entry["Comments Present"][src] = False
    if not (log_entry["Comments Present"].get("ex4a1.c") or log_entry["Comments Present"].get("ex4b1.c")):
        log_entry["Issues"].append("No comments in the first 10 lines of manager files (ex4a1.c/ex4b1.c).")
        deductions += POINTS['comments_missing']
        log_entry["Points Deducted"] += POINTS['comments_missing']

    ### Execution Phase – Concurrent Runs ###
    # --- Helper to start a process ---
    def start_proc(label, exe, arg_list, out_filename, submission_path):
        q = Queue()
        arg_list_str = [str(arg) for arg in arg_list]
        # Use stdbuf for unbuffered output.
        p = Process(target=run_program, args=(submission_path, exe, arg_list_str, out_filename, q))
        p.start()
        return p, q

    # --- Program A (Named Pipes) ---
    p_a_mgr, q_a_mgr = start_proc("Program A Manager", "ex4a1", ["fifom", "fifo0", "fifo1"], "ex4a1_output.txt", submission_path)
    time.sleep(2)  # Give manager time to set up.
    p_a_part0, q_a_part0 = start_proc("Program A Participant 0", "ex4a2", ["fifom", "0", "17"], "ex4a2_0_output.txt", submission_path)
    p_a_part1, q_a_part1 = start_proc("Program A Participant 1", "ex4a2", ["fifom", "1", "18"], "ex4a2_1_output.txt", submission_path)
    for proc, q, label in [(p_a_mgr, q_a_mgr, "Program A Manager"),
                           (p_a_part0, q_a_part0, "Program A Participant 0"),
                           (p_a_part1, q_a_part1, "Program A Participant 1")]:
        proc.join(timeout=TIMEOUT_EXECUTION + 10)
        if proc.is_alive():
            proc.terminate()
            log_entry["Execution Outputs"][label] = "Execution timed out."
            q.put("Execution timed out.")
        try:
            res = q.get_nowait()
        except Exception:
            res = "No Output"
        log_entry["Execution Outputs"][label] = res
        logging.info(f"{label} Output:\n{res}")

    # --- Program B (Message Queues) ---
    p_b_mgr, q_b_mgr = start_proc("Program B Manager", "ex4b1", [], "ex4b1_output.txt", submission_path)
    time.sleep(2)
    p_b_part0, q_b_part0 = start_proc("Program B Participant 0", "ex4b2", ["0", "17"], "ex4b2_0_output.txt", submission_path)
    p_b_part1, q_b_part1 = start_proc("Program B Participant 1", "ex4b2", ["1", "18"], "ex4b2_1_output.txt", submission_path)
    for proc, q, label in [(p_b_mgr, q_b_mgr, "Program B Manager"),
                           (p_b_part0, q_b_part0, "Program B Participant 0"),
                           (p_b_part1, q_b_part1, "Program B Participant 1")]:
        proc.join(timeout=TIMEOUT_EXECUTION + 10)
        if proc.is_alive():
            proc.terminate()
            log_entry["Execution Outputs"][label] = "Execution timed out."
            q.put("Execution timed out.")
        try:
            res = q.get_nowait()
        except Exception:
            res = "No Output"
        log_entry["Execution Outputs"][label] = res
        logging.info(f"{label} Output:\n{res}")

    # --- Program C (Servers and Frontend) ---
    # Start the two server processes concurrently.
    p_c_server1, q_c_server1 = start_proc("Program C Prime Server", "ex4c1", [], "ex4c1_output.txt", submission_path)
    p_c_server2, q_c_server2 = start_proc("Program C Arithmetic Server", "ex4c2", [], "ex4c2_output.txt", submission_path)
    time.sleep(2)
    # Create a temporary input file for the frontend.
    temp_input_file = os.path.join(submission_path, "ex4c3_test_input.txt")
    with open(temp_input_file, 'w') as finp:
        finp.write("p\n2 3897 100 17 0\n" + "a\n3879 + 17\n")
    # Launch the Frontend (ex4c3) with STDIN redirected from the temporary file.
    try:
        output_file = os.path.join(submission_path, "ex4c3_output.txt")
        cmd = ["stdbuf", "-o0", "./ex4c3"]
        logging.info(f"Running command: {' '.join(cmd)} in {submission_path} with input from file")
        with open(temp_input_file, 'r') as fin, open(output_file, 'w') as fout:
            p_c_frontend = subprocess.Popen(
                cmd,
                cwd=submission_path,
                stdin=fin,
                stdout=fout,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                start_new_session=True
            )
        # Allow the frontend to run briefly (2 seconds) to read the input.
        time.sleep(2)
        # Terminate the frontend immediately.
        try:
            os.killpg(os.getpgid(p_c_frontend.pid), signal.SIGINT)
            logging.info(f"Sent SIGINT to Program C Frontend (PID: {p_c_frontend.pid})")
        except Exception as e:
            logging.error(f"Failed to send SIGINT to Program C Frontend: {e}", exc_info=True)
        try:
            p_c_frontend.wait(timeout=5)
        except Exception:
            p_c_frontend.terminate()
        # Read only the first two lines of the output.
        with open(output_file, 'r') as fout:
            frontend_lines = []
            for _ in range(2):
                line = fout.readline()
                if not line:
                    break
                frontend_lines.append(line.strip())
        frontend_summary = "\n".join(frontend_lines)
        log_entry["Execution Outputs"]["Program C Frontend"] = f"ex4c3 Output (first 2 lines):\n{frontend_summary}"
        logging.info(f"Program C Frontend Output (first 2 lines):\n{frontend_summary}")
    except Exception as e:
        logging.error(f"Error running Program C Frontend: {e}", exc_info=True)
        log_entry["Execution Outputs"]["Program C Frontend"] = f"Execution Error: {e}"
    finally:
        try:
            os.remove(temp_input_file)
        except Exception as e:
            logging.warning(f"Could not remove temporary input file {temp_input_file}: {e}")

    # --- Termination Phase for Program C – Servers ---
    def terminate_process(proc, label, q):
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            logging.info(f"Sent SIGINT to {label} (PID: {proc.pid})")
        except Exception as e:
            logging.error(f"Failed to send SIGINT to {label}: {e}", exc_info=True)
        try:
            proc.join(timeout=5)
        except Exception:
            proc.terminate()
        try:
            q.put("Terminated after test.")
        except Exception:
            pass
        logging.info(f"{label} terminated after test.")
    for label, proc, q in [
            ("Program C Prime Server", p_c_server1, q_c_server1),
            ("Program C Arithmetic Server", p_c_server2, q_c_server2)
        ]:
        terminate_process(proc, label, q)
        try:
            res = q.get_nowait()
        except Exception:
            res = "No Output"
        log_entry["Execution Outputs"][label] = res
        logging.info(f"{label} Output:\n{res}")

    # Set final score.
    log_entry["Points Deducted"] = deductions
    log_entry["Final Score"] = max(TOTAL_POINTS - deductions, 0)
    return log_entry

### Generate JSON Summary ###
def generate_summary(summary, output_path):
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=4, ensure_ascii=False)
        logging.info(f"JSON summary generated at {output_path}")
    except Exception as e:
        logging.error(f"Failed to write JSON summary: {e}", exc_info=True)

### Main Function ###
def main():
    setup_logging()
    logging.info("Starting grading process for Exercise 4 (ex4).")
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(WORKDIR, exist_ok=True)
    
    summary_file = os.path.join(SUMMARY_DIR, 'summary_ex4.json')
    summary = []
    
    for submission_folder in os.listdir(SUBMISSIONS_DIR):
        submission_path = os.path.join(SUBMISSIONS_DIR, submission_folder)
        if not os.path.isdir(submission_path):
            logging.warning(f"Skipping non-directory item in submissions: {submission_folder}")
            continue
        logging.info(f"Processing submission folder: {submission_folder}")
        log = process_submission(submission_folder)
        # Avoid returning None in case of error.
        if log is None:
            continue
        summary.append(log)
        logging.info(f"Finished processing: {submission_folder} | Final Score: {log.get('Final Score', 'N/A')}")
    
    generate_summary(summary, summary_file)
    logging.info("Grading complete for Exercise 4 (ex4).")

if __name__ == "__main__":
    main()
