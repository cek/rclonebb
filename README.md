# rclonebb.py

Backup to Backblaze B2 using ``rclone``.

rclonebb was written to facilitate backing up a Truenas Core system to Backblaze B2.
The script can run ``rclone sync``, ``check``, or ``cryptcheck``, and email the results to a particular recipient.
A summary of the results, and an (optionally compressed) copy of the ``rclone`` log, can be emailed to a desired recipient.

This script was inspired by [rclonebackup](https://github.com/jaburt/rclonebackup), which works very well if you prefer using a shell script.

# Installation

* Create a B2 bucket to sync to.
* Set up rclone to work with Backblaze B2. Instructions can be found [here](https://rclone.org/b2). Note that if running on a Truenas system, you will want to store the resulting conf file someplace other than the default location.  A prototype `rclone.conf` file is included in this repo.
* You should encrypt your backups; details can be found [here](https://rclone.org/crypt).
* Optionally, create an rclone exclusion file, following the instructions [here](https://rclone.org/filtering).  An example exclusion file is included in this repo as well.
* Although `rclonebb` configuration-related options may be specified on the command line, it's usually easier to edit the script
and change the defaults. See the comments inline for details.
* Check that your configuration is correct by performing a dry run (``rclonebb.py sync --dry-run``)
* If running on a Truenas system, use the Trunas web interface to create a new Cron Job task that performs a sync at the desired intervals. Use ``Run Now`` to perform an initial sync.
* Determine if you want to run ``rsync cleanup`` after a successful sync. If so, set ``cleanup`` path appropriately.

# Use

``rclonebb.py sync [options]``: Sync the local directory to the remote bucket.

``rclonebb.py check [options]``: Check that the files in the local directory and remote bucket match.

``rclonebb.py cryptcheck [options]``: Check that the files in the local directory and encrypted remote bucket match.


# Options

```
  --local-dir LOCAL_DIR
  		        Local directory to be synced.
  --remote-bucket REMOTE_BUCKET
                        Remote bucket to sync to.
  --transfers TRANSFERS
                        Number of simultaneous transfers.
  --exclude-from EXCLUDE_FROM
                        File containing patterns of files or directories to be skipped.
  --email EMAIL         Email address to send the summary.
  --rclone-config RCLONE_CONFIG
                        Path to rclone configuration file.
  --compress-log        Compress the log file before attaching to email.
  --min-age MIN_AGE     Minimum age of files to be synced.
  --log-dir LOG_DIR     Directory to store the log files.
  --max-log-files MAX_LOG_FILES
                        Maximum number of log files to store. Oldest files will be deleted first.
  --dry-run             Perform a dry run. No changes will be made. Only effective in 'sync' mode.
  --cleanup_path        Path on which to perform ``rclone cleanup'' following a successful sync, if any.
```

# Duplicate files

Note that if a file is modified and synced to backblaze, backblaze will by deafult keep both old version and the new version. This behavior can be changed using the ``lifetime`` bucket settings to, for example, only store a single copy of a file. However, even with this setting, backblaze can store multiple copies of a file, as the earlier versions are first 'hidden' by backblaze's lifetime management implementation, before the files are eventually deleted.

To force immediate deletion of old file versions, specify a ``cleanup_path`` (e.g. ``/`` or ``/time-machine``), and rclonebb will run ``rclone cleanup`` with the appropriate arguments after a successful sync.

# References
* https://rclone.org
* https://backblaze.com/b2

