import os
import runpy

if __name__ == '__main__':
    official_server = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'backend', 'static-server', 'server.py'
    )
    runpy.run_path(official_server, run_name='__main__')