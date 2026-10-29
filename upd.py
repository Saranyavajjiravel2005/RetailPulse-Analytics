with open("frontend/src/routes/AppRoutes.tsx", "r") as f:
    content = f.read()
if "DataQuality" not in content:
    content = content.replace("import ScheduledReports from '../pages/reports/ScheduledReports';", 
        "import ScheduledReports from '../pages/reports/ScheduledReports';\nimport DataQuality from '../pages/data-quality/DataQuality';\nimport DataQualityIssueDetail from '../pages/data-quality/DataQualityIssueDetail';")
    old = "            <Route path=\"/reports/scheduled\" element={<ScheduledReports />} />\n          </Route>\n          <Route path=\"/profile\" element={<Profile />} />"
    new = "            <Route path=\"/reports/scheduled\" element={<ScheduledReports />} />\n            <Route path=\"/data-quality\" element={<DataQuality />} />\n            <Route path=\"/data-quality/issues/:issueId\" element={<DataQualityIssueDetail />} />\n          </Route>\n          <Route path=\"/profile\" element={<Profile />} />"
    content = content.replace(old, new)
    with open("frontend/src/routes/AppRoutes.tsx", "w") as f:
        f.write(content)
    print("ok")
else:
    print("exists")
