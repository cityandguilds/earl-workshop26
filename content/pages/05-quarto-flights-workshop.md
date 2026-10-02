---
id: quarto-flights-report
title: Publish a flights report with Quarto
slug: "quarto-flights-report"
order: 400
section: Quarto
section_order: 400
summary: "Query PostgreSQL, render a Quarto report, publish it with Nginx, and download it using SCP"
level: "Beginner"
estimated_minutes: 20
---

# Publish a flights report with Quarto

## Session goal

In this activity you will create a reproducible report from the flights data stored in PostgreSQL. You will render the report as HTML, publish it through Nginx, and retrieve a copy on your own computer using SCP.

## Learning outcomes

By the end of the activity, you should be able to:

- explain what Quarto does;
- combine Markdown, R code, and query results in a `.qmd` file;
- connect to PostgreSQL using protected environment variables;
- render a Quarto document to HTML;
- publish a static report through Nginx;
- transfer the rendered report with SCP.

## What is Quarto?

Quarto is an open-source publishing system for creating reports, presentations, websites, and books. A Quarto document can combine explanatory Markdown with executable code and its output.

Quarto renders source files such as `report.qmd` into formats including HTML, PDF, and Word. In this activity, the result is a self-contained HTML file that can be served by Nginx or copied to another computer.

The workflow is:

```text
PostgreSQL
    |
    v
R code in report.qmd
    |
    v
Quarto render
    |
    v
report.html
    |
    +---- Nginx ----> web browser
    |
    +---- SCP ------> local computer
```

## 0 to 3 minutes: check the tools and data

Confirm that Quarto and R are installed:

```bash
quarto --version
R --version
```

Confirm that your database configuration exists without displaying its contents:

```bash
test -r ~/.config/dsi/database.env
echo $?
```

An exit status of `0` confirms that the file is readable.

Load the settings into your shell and test the database:

```bash
set -a
source ~/.config/dsi/database.env
set +a

psql -c 'SELECT COUNT(*) FROM flights.route_details;'
```

## 3 to 6 minutes: create the report project

Create a working directory:

```bash
mkdir -p ~/quarto-flights
cd ~/quarto-flights
```

Create `report.qmd`:

````bash
cat > report.qmd <<'QMD'
---
title: "Flights report"
subtitle: "Routes from Manchester Airport"
author: "Workshop participant"
format:
  html:
    toc: true
    embed-resources: true
execute:
  echo: true
  warning: false
---

## Overview

This report queries the workshop PostgreSQL database and summarises routes from Manchester Airport.

```{r}
#| label: setup

library(DBI)
library(RPostgres)
library(ggplot2)

required_variables <- c(
  "PGHOST",
  "PGPORT",
  "PGDATABASE",
  "PGUSER",
  "PGPASSWORD"
)

missing_variables <- required_variables[
  Sys.getenv(required_variables) == ""
]

if (length(missing_variables) > 0) {
  stop(
    "Missing database settings: ",
    paste(missing_variables, collapse = ", ")
  )
}

con <- dbConnect(
  RPostgres::Postgres(),
  host = Sys.getenv("PGHOST"),
  port = as.integer(Sys.getenv("PGPORT")),
  dbname = Sys.getenv("PGDATABASE"),
  user = Sys.getenv("PGUSER"),
  password = Sys.getenv("PGPASSWORD")
)

on.exit(dbDisconnect(con), add = TRUE)
```

## Top destination countries

```{r}
#| label: query-countries

countries <- dbGetQuery(
  con,
  "
  SELECT
    destination_country,
    COUNT(*) AS route_count
  FROM flights.route_details
  WHERE source_airport_code = 'MAN'
    AND destination_country IS NOT NULL
  GROUP BY destination_country
  ORDER BY route_count DESC, destination_country
  LIMIT 10
  "
)

knitr::kable(
  countries,
  col.names = c("Destination country", "Routes")
)
```

## Route chart

```{r}
#| label: route-chart
#| fig-cap: "Ten countries with the most routes from Manchester"

ggplot(
  countries,
  aes(
    x = reorder(destination_country, route_count),
    y = route_count
  )
) +
  geom_col() +
  coord_flip() +
  labs(
    x = NULL,
    y = "Number of routes"
  )
```

## Example destinations

```{r}
#| label: query-destinations

routes <- dbGetQuery(
  con,
  "
  SELECT DISTINCT
    destination_airport_code,
    destination_city,
    destination_country
  FROM flights.route_details
  WHERE source_airport_code = 'MAN'
  ORDER BY destination_country, destination_city
  LIMIT 20
  "
)

knitr::kable(
  routes,
  col.names = c("Airport", "City", "Country")
)
```
QMD
````

The YAML header requests HTML output and `embed-resources: true`. This bundles supporting resources into one HTML file, making the result straightforward to publish and transfer.

## 6 to 11 minutes: render the report

The database variables must be available to the R process that Quarto starts. If you opened a new terminal, load them again:

```bash
set -a
source ~/.config/dsi/database.env
set +a
```

Render the document:

```bash
quarto render report.qmd
```

Confirm the output exists:

```bash
ls -lh report.html
```

Inspect the beginning of the generated file:

```bash
head -5 report.html
```

If rendering succeeds, `report.html` contains the narrative, query results, and chart created when the document was rendered. It does not query PostgreSQL when someone opens it in a browser.

## 11 to 15 minutes: publish through Nginx

Create a directory below the existing Nginx document root:

```bash
sudo install -d \
  -o root \
  -g root \
  -m 0755 \
  /var/www/html/reports
```

Install the rendered report:

```bash
sudo install \
  -o root \
  -g root \
  -m 0644 \
  report.html \
  /var/www/html/reports/flights.html
```

Test it locally on the VM:

```bash
curl --fail --silent \
  http://127.0.0.1/reports/flights.html \
  | head
```

Open the report in your browser, replacing the example host with your participant hostname:

```text
https://dsi-01.earl.sjp-analytics.co.uk/reports/flights.html
```

Nginx can serve this file using the existing `location /` block because `/var/www/html` is its configured document root.

## 15 to 18 minutes: retrieve the report with SCP

Run the following command on **your local computer**, not inside the VM. Replace the hostname if necessary:

```bash
scp \
  -i ~/.ssh/dsi-workshop \
  student@dsi-01.earl.sjp-analytics.co.uk:/var/www/html/reports/flights.html \
  ./flights.html
```

Confirm the local copy exists:

```bash
ls -lh ./flights.html
```

Open `flights.html` in a local browser. Because the report embeds its supporting resources, it can be viewed as a single transferred file.

## 18 to 20 minutes: make and publish a change

Change the report subtitle or adjust one of the SQL `LIMIT` values. Then repeat the publishing cycle:

```bash
set -a
source ~/.config/dsi/database.env
set +a

quarto render report.qmd

sudo install \
  -o root \
  -g root \
  -m 0644 \
  report.html \
  /var/www/html/reports/flights.html
```

Refresh the browser to see the updated report.

## Finished early?
Wondering how you could publish this on a recurring schedule if your database changes over time? Give us a shout and we can show you how to schedule a job to render updated reports.

## Troubleshooting

### Quarto cannot find an R package

Check the required packages:

```bash
Rscript -e '
packages <- c("DBI", "RPostgres", "ggplot2", "knitr")
print(vapply(packages, requireNamespace, logical(1), quietly = TRUE))
'
```

### Database settings are missing

Reload them before rendering:

```bash
set -a
source ~/.config/dsi/database.env
set +a
```

Do not print the password or commit `database.env` to source control.

### The SQL query fails

Test the same database connection outside Quarto:

```bash
psql -c '
SELECT destination_country, COUNT(*)
FROM flights.route_details
WHERE source_airport_code = $$MAN$$
GROUP BY destination_country
ORDER BY COUNT(*) DESC
LIMIT 5;
'
```

### The public report returns 404

Check the published file and the Nginx configuration:

```bash
sudo ls -l /var/www/html/reports/flights.html
sudo nginx -t
systemctl is-active nginx
```

### SCP reports permission denied

Confirm that you are running SCP from your local computer, using the participant hostname, the `student` account, and the correct private SSH key.

## Check your understanding

1. What is the difference between `report.qmd` and `report.html`?
2. When does the PostgreSQL query run?
3. Why are the database settings loaded into environment variables before rendering?
4. What does `embed-resources: true` provide?
5. Why is the published file installed with mode `0644`?
6. Which component serves `/reports/flights.html`?
7. In which direction does SCP transfer the file in this activity?

## Key takeaway

A Quarto source document combines narrative, code, and data access in a reproducible workflow. Rendering converts that source into a static HTML report, Nginx makes it available through the web, and SCP provides a direct way to retrieve the finished artifact.
