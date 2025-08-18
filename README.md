# hibernate-bind-visualizer-app

A Streamlit tool to visualize bound SQL queries from Hibernate TRACE logs.

## Local development

```bash
pip install -r requirements.txt
streamlit run hibernate_bind_visualizer_app.py
```

## Deployment on Railway

This repo includes a `Procfile` so Railway can launch the app:

```
web: streamlit run hibernate_bind_visualizer_app.py --server.port $PORT --server.address 0.0.0.0
```

To deploy:

1. Create a new project on [Railway](https://railway.app) and connect this repository.
2. Railway installs packages from `requirements.txt` and uses the `Procfile` to start the service.
3. Visit the generated URL to use the app.

## Deployment on Vercel

The repository also ships with a `vercel.json` so the app can run on Vercel's
Python runtime:

```
{
  "builds": [
    { "src": "hibernate_bind_visualizer_app.py", "use": "@vercel/python" }
  ],
  "routes": [
    { "src": "/(.*)", "dest": "hibernate_bind_visualizer_app.py" }
  ]
}
```

To deploy:

1. Push the repository to GitHub and import it into [Vercel](https://vercel.com).
2. Vercel installs dependencies from `requirements.txt` and launches the app
   using the configuration above.

