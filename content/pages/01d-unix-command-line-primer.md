---
id: unix
title: "Unix command-line primer"
slug: "unix-command-line-primer"
order: 40
section: "Getting started"
section_order: 40
summary: "Navigate files, copy work securely, and inspect a workshop VM from the terminal."
level: "Beginner"
estimated_minutes: 15
---

## What you will learn

By the end of this page, you should be able to:

- explain what Unix and a shell are;
- navigate the filesystem;
- create, copy, move, and remove files safely;
- transfer files with `scp`;
- perform basic process, memory, disk, and network checks.

> **Safety rule:** Read a command before pressing Enter. Commands such as `rm` may permanently remove files without using a recycle bin.

## Unix, Linux, terminal, and shell

**Unix** is a family of operating-system ideas and standards that influenced modern systems including Linux and macOS.

A **terminal** is the window or connection in which you type commands. A **shell** is the program that reads those commands. In this workshop you will usually use Bash on a Linux VM.

```text
You -> terminal -> shell -> operating system -> files and processes
```

## The command pattern

Many commands follow this pattern:

```text
command [options] [arguments]
```

For example:

```bash
ls -la /home/student
```

- `ls` is the command;
- `-la` contains options;
- `/home/student` is the argument.

Get help with:

```bash
command --help
man command
```

Press `q` to leave a `man` page.

## Where am I?

Show your current directory:

```bash
pwd
```

List its contents:

```bash
ls
ls -l
ls -la
```

Useful path symbols:

- `/` is the filesystem root;
- `~` is your home directory;
- `.` is the current directory;
- `..` is the parent directory;
- paths beginning with `/` are absolute;
- other paths are relative to your current directory.

## Move around

```bash
cd /home/student
cd ~
cd ..
cd -
```

Use Tab completion to reduce typing and spelling mistakes.

## Create directories and files

```bash
mkdir course-work
cd course-work
touch notes.txt
printf 'Hello, workshop!\n' > notes.txt
nano notes.txt
```

`>` replaces a file's contents. `>>` appends instead.

View a short text file:

```bash
cat notes.txt
less notes.txt
```

Press `q` to leave `less`.

## Copy, move, and rename

Copy a file:

```bash
cp notes.txt notes-backup.txt
```

Copy a directory and its contents:

```bash
cd ..
cp -r course-work course-work-backup
```

Move or rename a file:

```bash
cd course-work
mv notes.txt workshop-notes.txt
```

Move a file into another directory:

```bash
mkdir archive
mv workshop-notes.txt archive/
```

## Remove files carefully

Remove a file:

```bash
rm notes-backup.txt
```

Remove an empty directory:

```bash
rmdir empty-directory
```

Remove a directory and everything inside it:

```bash
rm -r old-directory
```

Before removing something, check the path:

```bash
pwd
ls -la old-directory
```

Avoid `rm -rf` while learning. It combines recursive deletion with forced deletion and can remove large amounts of data without prompting.

## Find files and text

Find files by name:

```bash
find . -name '*.py'
find ~/course-work -type f
```

Search inside text files:

```bash
grep 'FastAPI' README.md
grep -R 'localhost' .
```

## Understand permissions

Inspect permissions:

```bash
ls -l
```

A listing begins with characters such as:

```text
-rw-r--r--
```

These indicate the file type and permissions for the owner, group, and others.

Make a script executable:

```bash
chmod u+x script.sh
```

Do not use very broad permissions such as `chmod 777` as a quick fix. Find out which user needs which permission.

## Connect with SSH

From your own computer:

```bash
ssh -i /path/to/private-key student@your-workshop-hostname
```

- `-i` names the private key;
- `student` is the remote username;
- the hostname identifies the VM.

Keep the private key private. Do not upload it to Git or share it in messages.

## Copy files with scp

`scp` securely copies files over an SSH connection. Run these commands on your **local computer**, not inside the remote SSH session.

Copy a local file to the VM:

```bash
scp -i /path/to/private-key report.html \
  student@your-workshop-hostname:/home/student/
```

Copy a file from the VM to your computer:

```bash
scp -i /path/to/private-key \
  student@your-workshop-hostname:/home/student/report.html .
```

Copy a directory recursively:

```bash
scp -r -i /path/to/private-key course-work \
  student@your-workshop-hostname:/home/student/
```

The colon after the hostname separates the remote host from its remote path.

## Redirects and pipes

Save command output to a file:

```bash
ls -la > directory-listing.txt
```

Pass one command's output to another with a pipe:

```bash
ps aux | grep nginx
journalctl -u nginx --no-pager | tail -n 20
```

A pipe lets small tools work together.

## Basic system monitoring

### Identity and host

```bash
whoami
hostname
uname -a
```

### Disk space

```bash
df -h
du -sh ~
```

- `df -h` reports filesystem capacity;
- `du -sh ~` estimates space used by your home directory.

### Memory

```bash
free -h
```

### Processes

```bash
ps aux
top
```

Press `q` to leave `top`.

Find a process:

```bash
ps aux | grep '[n]ginx'
```

### Listening network ports

```bash
sudo ss -lntp
```

Useful letters here mean:

- `l`: listening;
- `n`: show numeric addresses and ports;
- `t`: TCP;
- `p`: owning process.

An address beginning with `127.0.0.1` is local to the VM. An address such as `0.0.0.0` listens on all IPv4 interfaces, although a cloud firewall may still block public access.

### Service status and logs

```bash
systemctl status nginx --no-pager
systemctl is-active nginx
journalctl -u nginx -n 50 --no-pager
```

### HTTP checks

```bash
curl http://localhost/healthz
curl -I http://localhost/
```

`curl -I` requests response headers, which are useful for checking status codes and redirects.

## A five-minute practice exercise

```bash
cd ~
mkdir -p command-practice/source
cd command-practice/source
printf 'first line\n' > example.txt
cp example.txt example-copy.txt
mv example-copy.txt renamed.txt
ls -la
cat renamed.txt
cd ..
du -sh .
```

When you are satisfied that you are in `~/command-practice`, clean up:

```bash
pwd
ls -la
cd ~
rm -r command-practice
```

## Common mistakes

- **Wrong directory:** run `pwd` before changing or removing files.
- **Spaces in names:** quote the path, as in `cd "Course Files"`.
- **Incorrect letter case:** `Report.html` and `report.html` are different names.
- **Local versus remote confusion:** the shell prompt and `hostname` tell you which machine you are using.
- **Permission denied:** inspect ownership and permissions before reaching for `sudo`.
- **Missing remote colon in scp:** `user@host:/path` is remote; `/path` alone is local.

## Check your understanding

1. What is the difference between an absolute and relative path?
2. Which command prints your current directory?
3. How do `cp` and `mv` differ?
4. Where should you run an `scp` command that downloads a file from the VM?
5. Which command displays listening TCP ports?
6. Why should you inspect a path before using `rm -r`?

## Key takeaway

The command line becomes manageable when you work in small steps: locate yourself, inspect the target, run one command, and verify the result.
