# visualizer

# Example in python
```python
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal

# referencing the service directly by its name (janusgraph, as defined in the docker compose file)
connection = DriverRemoteConnection('ws://janusgraph:8182/gremlin', 'g')
g = traversal().withRemote(connection)
g.V().count().next()
```