#!/usr/bin/env python
#
# rclonebb.py: Script to facilitate using rclone and Backblaze b2 as a backup mechanism
#
# https://github.com/cek/rclonebb
#
import os
import argparse
import smtplib, ssl
import pathlib
import json
import math
from email.message import EmailMessage
from datetime import datetime, timedelta
import gzip
import configparser

# Default values for command-line arguments

# Directory to sync
DEFAULT_LOCAL_DIR = "/mnt/data"
# B2 bucket
DEFAULT_REMOTE_BUCKET = "secret:/"
# Max number of simultaneous transfers
DEFAULT_TRANSFERS = 8
# rclone config and exclude files; see rclone docs for details
DEFAULT_RCLONE_CONFIG = "/mnt/data/rclonebb/rclone.conf"
DEFAULT_EXCLUDE_FILE = "/mnt/data/rclonebb/rclone_excludes.txt"
# Minimum file age to sync; helps avoid syncing open files
DEFAULT_MIN_AGE = "30m"
# Log file directory
DEFAULT_LOG_DIR = "/mnt/media/rclonebb/logs"
# Maximum number of log files to maintain in log directory. 0 = no limit
DEFAULT_MAX_LOG_FILES = 120
# Compress log file on completion?
DEFAULT_COMPRESS_LOG = True
# Address to which summary email should be sent; None or blank = no email sent
DEFAULT_RECIPIENT = "me@domain.com"
# Attach log file to email?
DEFAULT_ATTACH_LOG = False

# Email sender configuration
DEFAULT_SMTP_SERVER = 'smtp.domain.com'
DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_USERNAME = 'me@domain.com'
DEFAULT_SMTP_PASSWORD = 'password'

def rclone_backup(mode, local_dir, remote_bucket, transfers, exclude_file, rclone_config, min_age, log_dir, start_time, dry_run):
    # Ensure that the log directory exists
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    formatted_start_time = start_time.strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f"rclone_log_{formatted_start_time}.json")

    cmd = (f"rclone {mode} "
           f"--stats-file-name-length 0 "
           f"--use-json-log "
           f"--transfers {transfers} --log-level INFO --log-file {log_file} "
           f"--fast-list --links --b2-hard-delete --min-age {min_age}" )

    if dry_run:
        cmd += f" --dry-run"
    if rclone_config:
        cmd += f" --config={rclone_config}"
    if exclude_file:
        cmd += f" --exclude-from={exclude_file}"

    cmd += f" {local_dir} {remote_bucket}"
  
    os.system(cmd)
    
    return cmd, log_file

def maintain_log_files(log_dir, max_log_files):
    log_files = sorted([os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.startswith("rclone_log_")], key=os.path.getctime)
    while len(log_files) > max_log_files:
        os.remove(log_files.pop(0))  # remove the oldest log file

def send_email(subject, content, to_email, smtp_server, smtp_port, smtp_username, smtp_password, attachment_path=None):
    msg = EmailMessage()
    msg.set_content(content)
    msg['Subject'] = subject
    msg['From'] = smtp_username
    msg['To'] = to_email
    
    if attachment_path:
        with open(attachment_path, 'rb') as attachment:
            msg.add_attachment(attachment.read(), maintype='application', subtype='octet-stream', filename=os.path.basename(attachment_path))
  
    context = ssl.create_default_context() 
    with smtplib.SMTP(smtp_server, smtp_port) as smtp:
        smtp.starttls(context=context)
        smtp.login(smtp_username, smtp_password)
        smtp.send_message(msg)

def format_bytes(count):
    unit = "B"
    if count > 0:
        units = ["B", "KB", "MB", "GB", "TB"]
        idx = int(math.log(count, 1024))
        if idx < len(units):
            count /= 1024 ** idx
            unit = units[idx]
        else:
            count /= 1024 ** (len(units) - 1)
            unit = units[-1]
    return count, unit

def compress_logfile(log_file):
    compressed_log_file = log_file + ".gz"
    with open(log_file, 'rb') as log_in:
        with gzip.open(compressed_log_file, 'wb') as log_out:
            log_out.writelines(log_in)
    return compressed_log_file

def main():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    config = configparser.ConfigParser()
    config.read(os.path.join(script_dir, 'settings.ini'))

    local_dir = config.get('DEFAULT', 'local_dir', fallback=DEFAULT_LOCAL_DIR)
    remote_bucket = config.get('DEFAULT', 'remote_bucket', fallback=DEFAULT_REMOTE_BUCKET)
    transfers = config.getint('DEFAULT', 'transfers', fallback=DEFAULT_TRANSFERS)
    rclone_config = config.get('DEFAULT', 'rclone_config', fallback=DEFAULT_RCLONE_CONFIG)
    exclude_file = config.get('DEFAULT', 'exclude_file', fallback=DEFAULT_EXCLUDE_FILE)
    min_age = config.get('DEFAULT', 'min_age', fallback=DEFAULT_MIN_AGE)
    log_dir = config.get('DEFAULT', 'log_dir', fallback=DEFAULT_LOG_DIR)
    max_log_files = config.getint('DEFAULT', 'max_log_files', fallback=DEFAULT_MAX_LOG_FILES)
    compress_log = config.getboolean('DEFAULT', 'compress_log', fallback=DEFAULT_COMPRESS_LOG)
    email_recipient = config.get('DEFAULT', 'email_recipient', fallback=DEFAULT_RECIPIENT)
    attach_log = config.getboolean('DEFAULT', 'attach_log', fallback=DEFAULT_ATTACH_LOG)
    smtp_server = config.get('DEFAULT', 'smtp_server', fallback=DEFAULT_SMTP_SERVER)
    smtp_port = config.get('DEFAULT', 'smtp_port', fallback=DEFAULT_SMTP_PORT)
    smtp_username = config.get('DEFAULT', 'smtp_username', fallback=DEFAULT_SMTP_USERNAME)
    smtp_password = config.get('DEFAULT', 'smtp_password', fallback=DEFAULT_SMTP_PASSWORD)

    parser = argparse.ArgumentParser(description="Sync a directory to Backblaze B2 using rclone.")
    
    parser.add_argument("mode", type=str, choices=["sync", "check", "cryptcheck"],
                        help="Required. Mode of operation: sync, check or cryptcheck.")
    parser.add_argument("--local-dir", type=str, default=local_dir,
                        help=f"Local directory to be synced. Default: {local_dir}")
    parser.add_argument("--remote-bucket", type=str, default=remote_bucket,
                        help=f"Remote bucket to sync to. Default: {remote_bucket}")
    parser.add_argument("--transfers", type=int, default=transfers,
                        help=f"Number of simultaneous transfers. Default: {transfers}")
    parser.add_argument("--exclude-from", type=str, default=exclude_file,
                        help=f"File containing patterns of files or directories to be skipped. Default: {exclude_file if exclude_file else 'None'}")
    parser.add_argument("--email_recipient", type=str, default=email_recipient,
                        help=f"Email address to which to send the summary. Default: {email_recipient if email_recipient else 'None'}")
    parser.add_argument("--rclone-config", type=str, default=rclone_config,
                        help=f"Path to rclone configuration file. Default: {rclone_config if rclone_config else 'None'}")
    parser.add_argument("--compress-log", action="store_true", default=compress_log,
                        help=f"Compress the log file before attaching to email. Default: {compress_log}")
    parser.add_argument("--min-age", type=str, default=min_age,
                        help=f"Minimum age of files to be synced. Default: {min_age}")
    parser.add_argument("--log-dir", type=str, default=log_dir,
                        help=f"Directory to store the log files. Default: {log_dir}")
    parser.add_argument("--max-log-files", type=int, default=max_log_files,
                        help=f"Maximum number of log files to store. Oldest files will be deleted first. Default: {max_log_files}")
    parser.add_argument("--attach-log", action="store_true", default=attach_log,
                        help=f"Attach the log file to the email. Default: {attach_log}")
    parser.add_argument("--dry-run", action="store_true",
                        help="Perform a dry run. No changes will be made. Only effective in 'sync' mode.")

   
    args = parser.parse_args()
    
    exception_string = ""
    start_time = datetime.now()

    try:
        cmd, log_file = rclone_backup(args.mode, args.local_dir, args.remote_bucket, args.transfers, args.exclude_from, args.rclone_config, args.min_age, args.log_dir, start_time, args.dry_run)
    except Exception as e:
        exception_string += e + '\n'

    end_time = datetime.now()
    elapsed_time = end_time - start_time

    formatted_start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
    formatted_end_time = end_time.strftime('%Y-%m-%d %H:%M:%S')
    formatted_elapsed_time = str(elapsed_time).split('.')[0]
   
    summary = (f"Start time: {formatted_start_time}\n"
               f"Completion time: {formatted_end_time}\n"
               f"Elapsed time: {formatted_elapsed_time}\n\n"
               f"Command line: {cmd}\n\n")

    # Open the json file and parse the last info entry
    j = []
    last_info = []
    with open(log_file, 'r') as f:
        lines = f.readlines()
        try:
            last_info = json.loads(lines[-1])
        except Exception as e:
            summary += f"Error loading json: {e}\n"
            summary += f"Last line: {lines[-1]}\n"
    if not last_info:
        summary += f"Cannot parse log file {log_file}."
    if "message" in last_info:
        summary += f"{last_info['message']}\n"
    if "error" in last_info:
        summary += f"Error: {last_info['error']}\n"
    if "notice" in last_info:
        summary += f"Notice: {last_info['notice']}\n"
    if "fatal" in last_info:
        summary += f"Fatal: {last_info['fatal']}\n"
    if "debug" in last_info:
        summary += f"Debug: {last_info['debug']}\n"
    if "retry" in last_info:
        summary += f"Retry: {last_info['retry']}\n"
    if "warn" in last_info:
        summary += f"Warning: {last_info['warn']}\n"
    if "stats" in last_info:
        # Compute throughput from bytes and elapsed time
        bytes_transfered = int(last_info["stats"]["bytes"])
        elapsed_time = float(last_info["stats"]["elapsedTime"])
        throughput = bytes_transfered / elapsed_time
        throughput, throughputUnit = format_bytes(throughput)
        bytes_transfered, bytes_transferedUnit = format_bytes(bytes_transfered)

        deleted_files = last_info["stats"]["deletes"]
        deleted_dirs = last_info["stats"]["deletedDirs"]
        transferred_files = last_info["stats"]["transfers"]
        transfer_time = last_info["stats"]["transferTime"]
        checks = last_info["stats"]["checks"]
        speed = last_info["stats"]["speed"]
        summary += f"Checks: {checks}\n"
        summary += f"Transferred files: {transferred_files}\n"
        summary += f"Deleted files: {deleted_files}\n"
        summary += f"Deleted directories: {deleted_dirs}\n"
        summary += f"Transfered: {bytes_transfered:.3f} {bytes_transferedUnit}\n"
        summary += f"Elapsed time: {elapsed_time:.2f} sec\n"
        summary += f"Throughput: {throughput:.3f} {throughputUnit}/sec\n"
    else:
        summary += "No stats found.\n"

    if args.compress_log:
        try:
            compressed_log_file = compress_logfile(log_file)
            if compressed_log_file and os.path.exists(log_file):
                pathlib.Path(log_file).unlink()
                log_file = compressed_log_file
        except Exception as e:
            exception_string += e + '\n'

    if args.max_log_files > 0:
        try:
            maintain_log_files(args.log_dir, args.max_log_files)
        except Exception as e:
            exception_string += e + '\n'

    if args.email_recipient:
        summary += exception_string 
        email_subject = f"rclonebb {args.mode} summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        send_email(email_subject, summary, email_recipient, smtp_server, smtp_port, smtp_username, smtp_password, log_file if attach_log else None)

if __name__ == "__main__":
    main()

