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
      2. A dict mapping group names to lists of usernames (for group assignment later)

    Supported CSV columns:
      - name         (required) : the username or email used to log in
      - site_role    (optional) : defaults to 'Unlicensed' if left blank
      - email        (optional) : must be a valid email (if included)
      - auth_setting (optional) : identity provider for the user
                                  Valid values: ServerDefault, SAML, OpenID
                                  Defaults to ServerDefault if left blank
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

            # Set email only if the column exists and has a value
            if "email" in row and row["email"]:
                user.email = row["email"]

            # Set auth_setting if provided — controls which identity provider
            # authenticates this user. Defaults to ServerDefault if left blank.
            if "auth_setting" in row and row["auth_setting"]:
                user.auth_setting = row["auth_setting"]

            users.append(user)

            # --- Collect group assignments ---
            # Look for any column whose name starts with "group" (group1, group2, etc.)
            # If the cell has a value, record that this user belongs to that group.
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
    once complete. wait_for_job() handles polling for us so we don't
    have to manually check the status in a loop.
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

    Then compare every user on the site against the current list of added names.
    TSC.Pager handles pagination automatically — if there are more users
    than one page can hold, it keeps fetching until it has them all.
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

    # If you reach this point, the group wasn't found — Create it
    print(f"  Group '{group_name}' not found. Creating it...")
    new_group = TSC.GroupItem(name=group_name)
    return server.groups.create(new_group)


def assign_users_to_groups(server, group_assignments, user_id_map):
    """
    Assigns users to their groups based on the group_assignments dict.

    For each group, look it up on the site (or create it if it doesn't exist),
    then add each user one at a time. TSC doesn't currently have a bulk method
    for group membership the way it does for adding users, so we use a loop.

    Users with no group columns filled in are simply skipped — No action needed.
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
                # This shouldn't happen if the bulk add succeeded, but it's worth flagging
                print(f"  Warning: '{user_name}' not found in user ID map. Skipping.")


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
        print("The bulk add job did not complete successfully. Check your Tableau site for details.")
