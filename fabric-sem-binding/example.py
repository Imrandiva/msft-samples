import time
import notebookutils
import sempy.fabric as fabric

workspace = notebookutils.runtime.context["currentWorkspaceId"]
items = fabric.list_items(workspace=workspace)
bindings = [
    {"model": "Sales", "lakehouse": "Retail_LH_ALM",
     "expression": "DirectLake - Retail_LH", "reports": ["sales"]},
]

def item_id(kind, name):
    return items.loc[(items["Type"] == kind) & (items["Display Name"] == name), "Id"].item()

if len({binding["model"] for binding in bindings}) != len(bindings):
    raise ValueError("List each model once, with all its reports in the same entry.")

for binding in bindings:
    lakehouse = item_id("Lakehouse", binding["lakehouse"])
    model = item_id("SemanticModel", binding["model"])
    reports = [item_id("Report", name) for name in binding["reports"]]
    with fabric.connect_semantic_model(model, workspace=workspace, readonly=False) as tom:
        tom.model.Expressions[binding["expression"]].Expression = (
            f'let Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/{workspace}/{lakehouse}", [HierarchicalNavigation=true]) in Source'
        )
    for report in reports:
        fabric.PowerBIRestClient().post(
            f"/v1.0/myorg/groups/{workspace}/reports/{report}/Rebind",
            json={"datasetId": model},
        ).raise_for_status()

    refresh = fabric.refresh_dataset(model, workspace=workspace, refresh_type="full")
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        result = fabric.get_refresh_execution_details(model, refresh, workspace=workspace)
        if result.status == "Completed":
            break
        if result.status in {"Failed", "Cancelled", "Disabled"}:
            raise RuntimeError(f"{binding['model']} refresh failed: {result.status}; {result.messages}")
        time.sleep(5)
    else:
        raise TimeoutError(f"{binding['model']} refresh did not complete in 20 minutes.")
