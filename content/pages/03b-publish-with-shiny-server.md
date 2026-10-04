---
id: shiny-server-deployment
title: "Deploy shinyFlights with Shiny Server"
slug: "shiny-server-deployment"
order: 210
section: "Shiny"
section_order: 210
summary: "Deploy a Shiny application to Shiny Server and connect it to PostgreSQL"
level: "Beginner"
estimated_minutes: 30
---

## Session goal

In this session you will deploy an existing Shiny application instead of writing one from scratch.

The app reads the `flights.route_details` view created in the PostgreSQL session. It lets users choose a departure airport, filter destination countries, inspect routes, and view a chart.

You will practise two common ways to move application code to a server:

1. copy a local project with `scp`;
2. clone a public GitHub repository directly on the VM.

## Learning outcomes

By the end of the session, you should be able to:

- describe the UI, server, and reactive parts of a Shiny app;
- distinguish application code from configuration and secrets;
- test a Shiny app before deployment;
- copy a project to a VM with `scp`;
- deploy from a public Git repository;
- inspect Shiny Server logs;
- explain how Nginx routes public traffic to Shiny Server.

## Before the workshop host publishes the repository

The supplied code bundle contains a directory called `shinyFlights`. Create a separate public repository named `shinyFlights`, then add these files at its root:

```text
shinyFlights/
├── app.R
├── README.md
├── LICENSE
├── .gitignore
└── www/
    └── styles.css
```

Replace the placeholder repository address in this page before publication:

```text
https://github.com/YOUR-GITHUB-USERNAME/shinyFlights.git
```

Keeping the demonstration app separate from the workshop website makes it behave like an independently released open source project. Participants can clone, fork, or copy the application without downloading the workshop-site source.

## Architecture recap

```text
Browser
   |
   | HTTPS, public port 443
   v
Nginx
   |
   | local reverse proxy
   v
Shiny Server, 127.0.0.1:3838
   |
   | local PostgreSQL connection
   v
PostgreSQL, 127.0.0.1:5432
   |
   v
flights.route_details
```

Only Nginx is exposed as the public web entry point. Shiny Server and PostgreSQL remain on local addresses.

## 0 to 5 minutes: inspect the project

On your **local computer**, download the public repository:

```bash
git clone https://github.com/lizardburns/shinyFlights.git
cd shinyFlights
find . -maxdepth 2 -type f -print
```

Inspect the files:

- `app.R` defines the user interface and server behaviour;
- `www/styles.css` contains browser styling;
- `README.md` explains runtime requirements;
- `.gitignore` prevents common local files and environment files from being committed.

The app uses a parameterised query:

```sql
SELECT DISTINCT
  destination_code,
  destination_airport,
  destination_city,
  destination_country,
  airline_name
FROM flights.route_details
WHERE source_code = $1;
```

`$1` is a placeholder. The selected airport is sent separately as a query parameter instead of being pasted into the SQL text.

## 5 to 10 minutes: test locally on the VM

Connect to your participant VM:

```bash
ssh -i /path/to/participant-key \
  student@dsi-01.earl.sjp-analytics.co.uk
```

Clone the project into your home directory for testing:

```bash
cd ~
rm -rf shinyFlights-test
git clone https://github.com/lizardburns/shinyFlights.git \
  shinyFlights-test
cd shinyFlights-test
```

Tell the app to use your participant database configuration, then start it on a temporary local port:

```bash
export SHINYFLIGHTS_ENV="$HOME/.config/dsi/database.env"
R -e "shiny::runApp('.', host='127.0.0.1', port=3839)"
```

Leave that command running. In a second SSH session, check the response:

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:3839/ \
  | head
```

Return to the first session and press Ctrl+C to stop the test app.

## 10 to 17 minutes: simulate deployment with scp

The source project is currently on your local computer. Copy it to a temporary deployment directory on the VM.

Run this from your **local computer**:

```bash
scp -r -i /path/to/participant-key \
  ./shinyFlights \
  student@dsi-01.earl.sjp-analytics.co.uk:/tmp/shinyFlights
```

SSH to the VM and publish the copied directory:

```bash
ssh -i /path/to/participant-key \
  student@dsi-01.earl.sjp-analytics.co.uk
```

```bash
sudo rm -rf /srv/shiny-server/shinyFlights
sudo mv /tmp/shinyFlights /srv/shiny-server/shinyFlights
sudo chown -R shiny:shiny /srv/shiny-server/shinyFlights
sudo find /srv/shiny-server/shinyFlights -type d -exec chmod 0755 {} \;
sudo find /srv/shiny-server/shinyFlights -type f -exec chmod 0644 {} \;
```

Because the app project (package) uses {renv} to manage R dependencies - **recommended** - we need to do a little work to ensure the environment is set up correctly.

```bash
sudo su - shiny
cd /srv/shiny-server/shinyFlights
R
```

```R
# if your package has dependencies on packages installed from private GitHub
# repos, you may need to authenticate, e.g.
# Sys.setenv(GITHUB_PAT="your_pat")
renv::status()
renv::restore()
```

This simulates deploying one of your own projects from your laptop to a server.

## 17 to 22 minutes: provide database configuration safely

Shiny Server is configured to run applications as the `shiny` service account. It cannot read the student's private environment file.

Copy the settings to a service-owned location without placing credentials inside the Git repository:

```bash
sudo install -o root -g shiny -m 0640 \
  ~/.config/dsi/database.env \
  /etc/shiny-server/shinyFlights.env
```

Confirm permissions without displaying the secret values:

```bash
sudo ls -l /etc/shiny-server/shinyFlights.env
sudo -u shiny test -r /etc/shiny-server/shinyFlights.env
echo $?
```

An exit value of `0` means the `shiny` account can read the file.

> Never add `database.env` to Git or copy it into `/srv/shiny-server/shinyFlights`.

## 22 to 25 minutes: validate the deployed app

Test Shiny Server locally:

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:3838/shinyFlights/ \
  | head
```

If the request fails, inspect the service and app logs:

```bash
sudo journalctl -u shiny-server -n 50 --no-pager
sudo find /var/log/shiny-server -maxdepth 1 -type f \
  -name '*shinyFlights*' -print
```

Then inspect the newest matching log file:

```bash
sudo tail -n 80 /var/log/shiny-server/*shinyFlights*.log
```

## 25 to 28 minutes: redeploy directly with Git

Now replace the copied deployment with a clone from the public repository:

```bash
sudo rm -rf /srv/shiny-server/shinyFlights
sudo git clone \
  https://github.com/lizardburns/shinyFlights.git \
  /srv/shiny-server/shinyFlights
sudo chown -R shiny:shiny /srv/shiny-server/shinyFlights
sudo su - shiny
cd /srv/shiny-server/shinyFlights
R
```

Restore your R environment:

```R
# if your package has dependencies on packages installed from private GitHub
# repos, you may need to authenticate, e.g.
# Sys.setenv(GITHUB_PAT="your_pat")
renv::status()
renv::restore()
```

This illustrates a simple Git-based deployment. The repository provides versioned application code, while the VM provides its own database configuration.

For a later update:

```bash
sudo su - shiny
cd /srv/shiny-server/shinyFlights
git status
git fetch origin
# if you've got any uncommitted files in your working directory on the server
# that you want to keep, e.g. .env files, you might want to think about other
# ways to manage that but right now you're going to need to stash them before
# you pull
# git stash
git pull --ff-only
git stash origin
git status
R
```

Always check if there's been any update to your dependencies so you can stay in sync.

```R
# if your package has dependencies on packages installed from private GitHub
# repos, you may need to authenticate, e.g.
# Sys.setenv(GITHUB_PAT="your_pat")
renv::status()
# renv::restore()
```

Restart application process for changes to take effect:

```bash
touch restart.txt
```

## 28 to 30 minutes: browse through Nginx

Open the participant URL in your browser:

[Open shinyFlights](https://dsi-01.earl.sjp-analytics.co.uk/shiny/shinyFlights/)

The public path begins with `/shiny/` because Nginx forwards that path to Shiny Server:

```text
https://participant-host/shiny/shinyFlights/
            |               |
            |               +-- Shiny app directory
            +-- Nginx route to Shiny Server
```

The browser does not connect directly to port 3838. It connects to Nginx over HTTPS on port 443. Nginx then proxies the request to Shiny Server on the VM.

## Exercise: trace one interaction

Choose a departure airport in the app, then explain the sequence:

1. the browser sends the selected airport to the Shiny session;
2. Shiny invalidates the dependent reactive expression;
3. R sends a parameterised query to PostgreSQL;
4. PostgreSQL queries `flights.route_details`;
5. Shiny rebuilds the summary, chart, and table;
6. the updated outputs return through Shiny Server and Nginx.

## Exercise: make and deploy a small change

On your local clone, change the page subtitle in `app.R`:

```r
p("Explore direct routes from the OpenFlights workshop database.")
```

For the `scp` route, copy the project again and repeat the publish commands.

For the Git route:

1. commit and push the change to your own public fork;
2. run `git pull --ff-only` in the deployed directory;
3. restart the application;
4. reload the application.

This demonstrates the path from source change to deployed application.

## Troubleshooting

### The app displays an error

Check the application log:

```bash
sudo tail -n 80 /var/log/shiny-server/*shinyFlights*.log
```

Common causes include:

- the `flights.route_details` view does not exist;
- the service account cannot read its environment file;
- an R package is missing;
- the database credentials are incorrect;
- PostgreSQL is not running.

### Check the database view

```bash
set -a
source ~/.config/dsi/database.env
set +a
psql -c 'SELECT COUNT(*) FROM flights.route_details;'
```

### Check services and listening ports

```bash
systemctl is-active postgresql
systemctl is-active shiny-server
systemctl is-active nginx
sudo ss -lntp | grep -E ':(3838|443)'
```

### A direct Shiny request works, but the public URL does not

Test the two layers separately:

```bash
curl -I http://127.0.0.1:3838/shinyFlights/
curl -I https://dsi-01.earl.sjp-analytics.co.uk/shiny/shinyFlights/
```

If the first succeeds and the second fails, investigate Nginx rather than the Shiny application.

## Check your understanding

1. Why is the database environment file not stored in Git?
2. Why must the `shiny` account be able to read the deployed files?
3. What is the difference between copying with `scp` and cloning with Git?
4. Which service accepts the public HTTPS connection?
5. Why is PostgreSQL not exposed on a public port?
6. What causes the plot and table to update when an airport changes?

## Key takeaway

Deployment separates versioned application code from server-specific configuration. GitHub distributes the code, Shiny Server runs it, PostgreSQL supplies the data, and Nginx provides the public HTTPS entry point.
