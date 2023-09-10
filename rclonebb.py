#!/usr/bin/env python
#
# rclonebb.py: Script to facilitate using rclone and Backblaze b2 as a backup mechanism
#
# https://github.com/cek/rclonebb
#
import os
import argparse
import smtplib, ssl
from email.message import EmailMessage
from datetime import datetime, timedelta
import gzip

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
DEFAULT_EMAIL = "me@domain.com"

# Email sender configuration
SMTP_SERVER = 'smtp.domain.com'
SMTP_PORT = 587
SMTP_SENDER_EMAIL = 'me@domain.com'
SMTP_SENDER_PASSWORD = 'password'

def rclone_backup(mode, local_dir, remote_bucket, transfers, exclude_file, rclone_config, min_age, log_dir, start_time, dry_run):
    # Ensure that the log directory exists
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    formatted_start_time = start_time.strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f"rclone_log_{formatted_start_time}.txt")

    cmd = (f"rclone {mode} "
           f"--stats-file-name-length 0 "
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

def send_email(subject, content, to_email, attachment_path=None):
    msg = EmailMessage()
    msg.set_content(content)
    msg['Subject'] = subject
    msg['From'] = SMTP_SENDER_EMAIL
    msg['To'] = to_email
    
    if attachment_path:
        with open(attachment_path, 'rb') as attachment:
            msg.add_attachment(attachment.read(), maintype='application', subtype='octet-stream', filename=os.path.basename(attachment_path))
  
    context = ssl.create_default_context() 
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.starttls(context=context)
        smtp.login(SMTP_SENDER_EMAIL, SMTP_SENDER_PASSWORD)
        smtp.send_message(msg)

def compress_log(log_file):
    compressed_log_file = log_file + ".gz"
    with open(log_file, 'rb') as log_in:
        with gzip.open(compressed_log_file, 'wb') as log_out:
            log_out.writelines(log_in)
    return compressed_log_file

def main():
    parser = argparse.ArgumentParser(description="Sync a directory to Backblaze B2 using rclone.")
    
    parser.add_argument("mode", type=str, choices=["sync", "check", "cryptcheck"],
                        help="Required. Mode of operation: sync, check or cryptcheck.")
    parser.add_argument("--local-dir", type=str, default=DEFAULT_LOCAL_DIR,
                        help=f"Local directory to be synced. Default: {DEFAULT_LOCAL_DIR}")
    parser.add_argument("--remote-bucket", type=str, default=DEFAULT_REMOTE_BUCKET,
                        help=f"Remote bucket to sync to. Default: {DEFAULT_REMOTE_BUCKET}")
    parser.add_argument("--transfers", type=int, default=DEFAULT_TRANSFERS,
                        help=f"Number of simultaneous transfers. Default: {DEFAULT_TRANSFERS}")
    parser.add_argument("--exclude-from", type=str, default=DEFAULT_EXCLUDE_FILE,
                        help=f"File containing patterns of files or directories to be skipped. Default: {DEFAULT_EXCLUDE_FILE if DEFAULT_EXCLUDE_FILE else 'None'}")
    parser.add_argument("--email", type=str, default=DEFAULT_EMAIL,
                        help=f"Email address to send the summary. Default: {DEFAULT_EMAIL}")
    parser.add_argument("--rclone-config", type=str, default=DEFAULT_RCLONE_CONFIG,
                        help=f"Path to rclone configuration file. Default: {DEFAULT_RCLONE_CONFIG if DEFAULT_RCLONE_CONFIG else 'None'}")
    parser.add_argument("--compress-log", action="store_true", default=DEFAULT_COMPRESS_LOG,
                        help="Compress the log file before attaching to email.")
    parser.add_argument("--min-age", type=str, default=DEFAULT_MIN_AGE,
                        help=f"Minimum age of files to be synced. Default: {DEFAULT_MIN_AGE}")
    parser.add_argument("--log-dir", type=str, default=DEFAULT_LOG_DIR,
                        help=f"Directory to store the log files. Default: {DEFAULT_LOG_DIR}")
    parser.add_argument("--max-log-files", type=int, default=DEFAULT_MAX_LOG_FILES,
                        help=f"Maximum number of log files to store. Oldest files will be deleted first. Default: {DEFAULT_MAX_LOG_FILES}")
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

    if args.max_log_files > 0:
        try:
            maintain_log_files(args.log_dir, args.max_log_files)
        except Exception as e:
            exception_string += e + '\n'

    with open(log_file, 'r') as f:
        lines = f.readlines()
    
    error_notices = [line for line in lines if "ERROR" in line or "NOTICE" in line]
    error_notices_text = "\n".join(error_notices)

    formatted_start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
    formatted_end_time = end_time.strftime('%Y-%m-%d %H:%M:%S')
    formatted_elapsed_time = str(elapsed_time).split('.')[0]
   
    summary = (f"Start time: {formatted_start_time}\n"
               f"Completion time: {formatted_end_time}\n"
               f"Elapsed time: {formatted_elapsed_time}\n\n"
               f"Command line: {cmd}\n\n")

    if args.mode == "sync":
        last_lines = "".join(lines[-6:])
        
        new_files = sum(1 for line in lines if ": Copied (new)" in line)
        replaced_files = sum(1 for line in lines if ": Copied (replaced" in line)
        deleted_files = sum(1 for line in lines if ": Deleted" in line)
        
        summary += (f"Summary of rclone sync:\n"
                    f"New files synced: {new_files}\n"
                    f"Files replaced: {replaced_files}\n"
                    f"Files deleted: {deleted_files}\n\n"
                    f"Rclone statistics:\n{last_lines}\n\n")

    if len(error_notices_text) > 0:
        summary += (f"ERRORs and NOTICEs:\n{error_notices_text}\n\n")

    if args.compress_log:
        try:
           log_file = compress_log(log_file)
        except Exception as e:
            exception_string += e + '\n'

    if args.email:
        summary += exception_string 
        email_subject = f"rclonebb {args.mode} summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        send_email(email_subject, summary, args.email, log_file)

if __name__ == "__main__":
    main()

