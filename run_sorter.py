import sys
import sorter

def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    pat_path = sys.argv[2] if len(sys.argv) > 2 else "patterns.yaml"
    sorter.process_all(cfg_path, pat_path)

if __name__ == "__main__":
    main()
