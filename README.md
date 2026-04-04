# Tableau Bulk Permissions Tutorial (DDQ2026-02 Beginner Challenge)

**Challenge:** [#DDQ2026-02 Bulk Add Users (Beginner)](https://datadevquest.com/challenges/ddq2026-02-bulk-add-users-beginner)  
**Author:** Joshua Vijeh ([@DataDevDiary](https://datadevdiary.com))  
**API Types:** REST API · TSC  
**Difficulty:** Beginner + Extra Challenge

---

## Overview

This tutorial is based on a solution to the DataDevQuest.com beginner challenge (DDQ2026-02) created by Jordan Woods.  The tutorial demonstrates how to use the `bulk_add` feature introduced in **TSC v0.40** to add multiple users to a Tableau Cloud site in a single request from a CSV file.

The solution follows the following steps:

```
Read CSV → Build UserItems → Bulk Add → Track Job → Retrieve User IDs → Assign to Groups
```

---

## Project Structure

```
tableau-bulk-permissions-tutorial/
├── .env                  # PAT credentials (excluded from version control)
├── .gitignore            # Ensures .env is never committed
├── users.csv             # Input file with users to add
├── bulk_add_users.py     # Main script
└── README.md
```

---

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) or pip
- A Tableau Cloud site (a free [Developer Sandbox](https://www.tableau.com/developer/get-site) will work if you do not have access to a Tableau Cloud site)
- A Personal Access Token (PAT) for your Tableau site

> **Note on Using the Developer Sandbox:** A Tableau Developer site only supports 1 Creator, 1 Explorer, and 1 Viewer. Therefore, any additional users will need to be added as `Unlicensed`. This exercise assumes you are using the Developer site, and therefore is reflected as such in the sample csv file.

---

## Installation (two possible options)

### Using uv

```bash
uv add "tableauserverclient>=0.40" python-dotenv
```

### Using pip

```bash
pip install "tableauserverclient>=0.40" python-dotenv
```

---

## Configuration

Create a `.env` file in the project root with your own Tableau credentials (template below):

```env
TABLEAU_SERVER_URL=https://prod-useast-a.online.tableau.com
TABLEAU_SITE_ID=your-site-name
TABLEAU_PAT_NAME=your-pat-name
TABLEAU_PAT_VALUE=your-pat-value
```

Make sure your `.gitignore` includes `.env` so credentials are never accidentally committed:

```
.env
```

---

## Input File

The script reads from `users.csv`. The only required column is `name` — all others are optional.

| Column | Required | Description |
|---|---|---|
| `name` | ✅ | Username or email used to log in |
| `site_role` | ➖ | Defaults to `Unlicensed` if omitted |
| `email` | ➖ | Must be a valid email if provided |
| `auth_setting` | ➖ | Identity provider: `ServerDefault`, `SAML`, or `OpenID`. Defaults to `ServerDefault` |
| `group1`, `group2`, ... | ➖ | Group name(s) to assign the user to (admin preference). Add as many columns as needed. Leave blank if the user does not belong to a group. |

### Sample CSV

```csv
name,email,site_role,auth_setting,group1,group2
viewer1@example.com,viewer1@example.com,Viewer,ServerDefault,Sales Team,
explorer1@example.com,explorer1@example.com,Explorer,SAML,Sales Team,Marketing Team
user3@example.com,user3@example.com,Unlicensed,ServerDefault,,
user4@example.com,user4@example.com,Unlicensed,OpenID,Marketing Team,
```

A few things worth noting in this example:
- `explorer1` belongs to two groups — both `group1` and `group2` are filled in
- `user3` has no group assignments — both group columns are blank, and the script skips the group step for that user
- `explorer1` authenticates via SAML and `user4` via OpenID — mixed identity providers in the same CSV are supported

---

## How to Run

```bash
python bulk_add_users.py
```

You should see output similar to:

```
Submitting bulk add request for 4 user(s)...
Job submitted. Job ID: a1b2c3d4-e5f6-...
Waiting for job to complete...
Job finished with status: Success

Retrieving user IDs for newly added users...

Successfully added users:
  viewer1@example.com: 9f3a1b2c-...
  explorer1@example.com: 4d7e8f1a-...
  user3@example.com: 2c5b9d3e-...
  user4@example.com: 1a4f6e8b-...

Assigning users to groups...

Processing group: 'Sales Team'
  Found existing group: 'Sales Team'
  Added 'viewer1@example.com' to 'Sales Team'
  Added 'explorer1@example.com' to 'Sales Team'

Processing group: 'Marketing Team'
  Group 'Marketing Team' not found. Creating it...
  Added 'explorer1@example.com' to 'Marketing Team'
  Added 'user4@example.com' to 'Marketing Team'
```

---

## The Code

```python
import csv
import os
import tableauserverclient as TSC
from dotenv import load_dotenv

# Load credentials from .env file
load_dotenv()

TABLEAU_SERVER_URL = os.getenv("TABLEAU_SERVER_URL")
SITE_ID = os.getenv("TABLEAU_SITE_ID")
PAT_NAME = os.getenv("TABLEAU_PAT_NAME")
PAT_VALUE = os.getenv("TABLEAU_PAT_VALUE")


def load_users_from_csv(filepath):
    """
    Reads a CSV file and returns two things:
      1. A list of TSC UserItem objects ready to be added to Tableau
      2. A dict mapping group names to lists of usernames (for assinging to groups)

    CSV columns:
      - name         (required) : the username or email used to log in
      - site_role    (optional) : defaults to Unlicensed if not provided
      - email        (optional) : must be a valid email if included
      - auth_setting (optional) : identity provider for the user
                                  Valid values: ServerDefault, SAML, OpenID
                                  Defaults to ServerDefault if not provided
      - group1, group2, group3  : optional group columns — add as many as needed.
                                  Leave blank if the user doesn't belong to a group.
    """
    users = []

    # group_assignments maps group_name -> list of user names belonging to that group
    group_assignments = {}

    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:

            # --- Build the UserItem ---
            user = TSC.UserItem(
                name=row["name"],
                site_role=row.get("site_role", TSC.UserItem.Roles.Unlicensed)
            )

            # Set an email only if the column exists and contains a value
            if "email" in row and row["email"]:
                user.email = row["email"]

            # Set auth_setting if provided — controls which identity provider
            # authenticates this user. Defaults to ServerDefault if left blank.
            if "auth_setting" in row and row["auth_setting"]:
                user.auth_setting = row["auth_setting"]

            users.append(user)

            # --- Collect group assignments ---
            # Look for any column whose name starts with "group" (group1, group2, etc.)
            # If the cell has a value, record that this user belongs to that group.  This
            # avoids having to modify code to include new groups added later.
            for col_name, value in row.items():
                if col_name.startswith("group") and value.strip():
                    group_name = value.strip()
                    if group_name not in group_assignments:
                        group_assignments[group_name] = []
                    group_assignments[group_name].append(row["name"])

    return users, group_assignments


def bulk_add_and_wait(server, users):
    """
    Submits a bulk add request to Tableau and waits for it to finish.

    bulk_add() returns a background job — Tableau processes user creation
    once compelete. wait_for_job() handles polling for you don't have to
    manually check the status in a loop.
    """
    print(f"Submitting bulk add request for {len(users)} user(s)...")

    job = server.users.bulk_add(users)
    print(f"Job submitted. Job ID: {job.id}")
    print("Waiting for job to complete...")

    completed_job = server.jobs.wait_for_job(job)
    print(f"Job finished with status: {completed_job.status}")

    return completed_job


def get_added_user_ids(server, user_names):
    """
    After users are added, retrieves their IDs from the site.

    Every user on the site is compared against the list of added names.
    TSC.Pager handles pagination automatically — if there are more users
    than one page can hold, it keeps fetching until it has all of them.
    """
    print("\nRetrieving user IDs for newly added users...")
    user_id_map = {}

    # TSC.Pager handles pagination so we don't have to manage page sizes manually
    for user in TSC.Pager(server.users):
        if user.name in user_names:
            user_id_map[user.name] = user.id

    return user_id_map


def get_or_create_group(server, group_name):
    """
    Looks up a group by name on the site. If it doesn't exist, creates it.
    Returns the GroupItem so we can add users to it.

    This handles cases where a group referenced in the CSV hasn't been
    created on the Tableau site yet.
    """
    # Page through all groups on the site and look for a name match
    for group in TSC.Pager(server.groups):
        if group.name == group_name:
            print(f"  Found existing group: '{group_name}'")
            return group

    # If we get here, the group wasn't found — create it
    print(f"  Group '{group_name}' not found. Creating it...")
    new_group = TSC.GroupItem(name=group_name)
    return server.groups.create(new_group)


def assign_users_to_groups(server, group_assignments, user_id_map):
    """
    Assigns users to their groups based on the group_assignments dict.

    For each group, look them up on the site (or create it if it doesn't exist),
    then add each user one at a time. TSC doesn't currently have a bulk method
    for group membership like it does for adding users.  Therefore a loop is
    needed.

    Users with no group columns filled in are skipped — no action needed.
    """
    if not group_assignments:
        print("\nNo group assignments found in CSV. Skipping group assignment step.")
        return

    print("\nAssigning users to groups...")

    for group_name, user_names in group_assignments.items():
        print(f"\nProcessing group: '{group_name}'")

        # Get the group from Tableau, or create it if it doesn't exist yet
        group = get_or_create_group(server, group_name)

        for user_name in user_names:
            if user_name in user_id_map:
                # Add the user to the group using their Tableau user ID
                server.groups.add_user(group, user_id_map[user_name])
                print(f"  Added '{user_name}' to '{group_name}'")
            else:
                # This shouldn't happen if the bulk add is successful, but it is 
                # worth flagging
                print(f"  Warning: '{user_name}' not found in user ID map. Therefore skip.")


# --- Main Script ---

# Set up authentication using a Personal Access Token (PAT)
# PATs are preferred over username/password for automation
tableau_auth = TSC.PersonalAccessTokenAuth(
    token_name=PAT_NAME,
    personal_access_token=PAT_VALUE,
    site_id=SITE_ID
)
server = TSC.Server(TABLEAU_SERVER_URL, use_server_version=True)

# Load users and group assignments from the CSV file
# The function returns both at once as a tuple
users_to_add, group_assignments = load_users_from_csv("users.csv")

# Sign in, run the workflow, then sign out automatically when the block ends
with server.auth.sign_in(tableau_auth):

    # Step 1: Bulk add all users and wait for the background job to finish
    completed_job = bulk_add_and_wait(server, users_to_add)

    if completed_job.status == "Success":

        # Step 2: Retrieve the Tableau-assigned IDs for the newly added users
        added_names = [user.name for user in users_to_add]
        user_ids = get_added_user_ids(server, added_names)

        print("\nSuccessfully added users:")
        for name, uid in user_ids.items():
            print(f"  {name}: {uid}")

        # Step 3: Assign users to groups (if any group columns were in the CSV)
        assign_users_to_groups(server, group_assignments, user_ids)

    else:
        print("The bulk add job did not complete successfully. Be sure to check your Tableau site for details.")

```

---

## Key Concepts

### Why did you use `bulk_add` instead of individual add requests?
Typically the approach is calling the Add User endpoint once per user in a loop. For large batches however, this is slow and puts unnecessary load on the server. The `bulk_add` method introduced in TSC v0.40 bundles all users into a single request, which Tableau processes as a background job.

### What is an async background job?
When you call `server.users.bulk_add()`, Tableau doesn't process the users immediately — it queues the work as a background job and returns a job ID. The `server.jobs.wait_for_job()` method takes care of querying Tableau until that job finishes, to avoid having to write a manual retry loop.

### What is `TSC.Pager`?
Tableau's API returns results in pages, meaning if you have more users or groups than the default page size, you'd only be able to see the first batch. `TSC.Pager` wraps any list endpoint and automatically fetches all pages for you. That way you always get the complete result set without having to write additional code.

### Why does `load_users_from_csv` return two items?
The function returns a tuple — `(users, group_assignments)`. This lets you collect everything you need from the CSV in a single run, without reading the file twice. The `users` list goes straight into the bulk add call; `group_assignments` is held until after the job completes and we have user IDs to work with.

### Why does group assignment happen after the bulk add?
Users cannot be assigned to groups until they exist on the site — and they don't exist until the background job finishes. That's why group assignment is always the last step in the process.

### What happens if a user does not have a group?
Nothing — and that's on purpose. If all of a user's group columns are blank, they simply won't appear in `group_assignments` and the group step skips them completely.

### What happens if a group doesn't exist yet?
The `get_or_create_group` function goes through all groups on the site looking for a name match. If it doesn't find one, it creates the group automatically before adding users to it. This means you don't have to create groups ahead of time in Tableau before running the script.

### What is `auth_setting` and when does it matter?
The `auth_setting` controls which identity provider (IdP) authenticates a user. The three valid values are:

| Value | When to use |
|---|---|
| `ServerDefault` | User authenticates however the site is configured (most common) |
| `SAML` | User authenticates via a SAML identity provider |
| `OpenID` | User authenticates via an OpenID Connect provider |

If left blank in the CSV, the script defaults to `ServerDefault`. Mixed values in the same CSV are allowed — each user's `auth_setting` is set independently.

---

## Video Walkthrough

*Coming soon — link will be added here.*

---

## Supporting Resources

- [TSC Docs – Bulk Add Users](https://tableau.github.io/server-client-python/docs/api-ref#usersbulk_add)
- [TSC Docs – Groups](https://tableau.github.io/server-client-python/docs/api-ref#groups)
- [Tableau REST API – Add User to Site](https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_ref_users_and_groups.htm#add_user_to_site)
- [Tableau REST API – Add User to Group](https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_ref_users_and_groups.htm#add_user_to_group)
- [Tableau Server Client for Python (PyPI)](https://pypi.org/project/tableauserverclient/)
- [Postman Collection for Tableau REST APIs](https://www.postman.com/salesforce-developers/salesforce-developers/collection/x06mp2m/tableau-apis)
