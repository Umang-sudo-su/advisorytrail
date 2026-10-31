import asyncio
import json
import logging

logger = logging.getLogger(__name__)

# WHAT THIS IS: An asynchronous function that accepts a folder path (where the code lives),
# runs the OSV-Scanner tool against it, and returns the vulnerabilities as a Python dictionary.
async def run_osv_scanner(directory_path: str) -> dict:
    logger.info(f"Starting OSV-Scanner on directory: {directory_path}")
    
    # 1. SPAWN THE BACKGROUND PROCESS
    # 'create_subprocess_exec' acts exactly like typing into a terminal.
    # Argument 1: "osv-scanner" (The tool we are calling)
    # Argument 2: "--json" (Forces the tool to output computer-readable JSON instead of human-readable text)
    # Argument 3: "-r" (Recursive flag: tells the scanner to look in all sub-folders)
    # Argument 4: directory_path (The target folder to scan)
    # stdout/stderr=PIPE: This captures the terminal output and error messages into Python's memory.
    try:
        process = await asyncio.create_subprocess_exec(
            "osv-scanner",
            "--json",
            "-r",
            directory_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError:
        # This triggers if the OSV-Scanner tool is not installed on the computer running the server
        logger.error("osv-scanner command not found. Is it installed?")
        return {"results": []}

    # 2. WAIT FOR COMPLETION AND CAPTURE DATA
    # 'communicate()' pauses this specific function until the scanner finishes analyzing the files.
    # It returns a tuple containing the standard output (results) and standard error (crashes).
    stdout, stderr = await process.communicate()
    
    # 3. PARSE THE TERMINAL OUTPUT
    # If the scanner produced output (stdout), we process it.
    if stdout:
        try:
            # terminal output is returned as raw bytes (like b'{"results":[]}').
            # We decode() it into a standard string, then use json.loads() to convert it into a Python dictionary.
            parsed_data = json.loads(stdout.decode('utf-8'))
            return parsed_data
        except json.JSONDecodeError:
            # If the tool spits out an error instead of JSON, we catch the crash here so the server doesn't break.
            logger.error(f"Failed to parse OSV JSON. Raw output: {stdout.decode('utf-8')}")
            return {"results": []}
            
    # If there is no standard output but there is an error message, log the failure.
    if stderr:
        logger.error(f"OSV-Scanner execution error: {stderr.decode('utf-8')}")
        
    # Always return a safe default dictionary structure if something fails, 
    # so the rest of the application doesn't crash when expecting data.
    return {"results": []}
