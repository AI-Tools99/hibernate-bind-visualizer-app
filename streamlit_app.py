from hibernate_bind_visualizer_app import main

# Streamlit executes the script with a module name other than "__main__".
# Calling main() at import time ensures the UI renders in all environments,
# including platforms like Vercel that simply run this script.
main()
