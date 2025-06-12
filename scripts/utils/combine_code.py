import os
import sys

def combine_files_to_txt(output_filename="full_code_text.txt", target_directory="."):
    """
    Combines content of .py, .yml, and README.md files in the target directory
    into a single txt file, wrapping each file's content with XML-like tags.

    Args:
        output_filename (str): The name of the output text file.
        target_directory (str): The directory to scan for files. Defaults to the
                                 directory where the script is located.
    """
    # If the target directory is ".", resolve it to the script's directory
    # This ensures it works correctly even if run from a different CWD
    if target_directory == ".":
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0])) # sys.argv[0] is the script name
        target_directory = script_dir
    else:
        # Ensure the target directory path is absolute for clarity
        target_directory = os.path.abspath(target_directory)

    output_filepath = os.path.join(target_directory, output_filename)
    files_processed_count = 0

    print(f"Scanning directory: {target_directory}")
    print(f"Output will be written to: {output_filepath}")

    try:
        # Open the output file in write mode with UTF-8 encoding
        with open(output_filepath, 'w', encoding='utf-8') as outfile:
            # Add the introductory sentence at the beginning of the file
            outfile.write("Here are the full code\n\n") # Add two newlines for separation

            # Iterate through all items in the target directory
            for filename in os.listdir(target_directory):
                # Construct the full path to the item
                filepath = os.path.join(target_directory, filename)

                # Check if it's a file and if it matches the desired types
                if os.path.isfile(filepath):
                    if filename.endswith(".py") or filename.endswith(".yml") or filename.lower() == "readme.md":
                        print(f"  Processing: {filename}...")
                        files_processed_count += 1

                        # Construct the XML-like tags using the filename
                        start_tag = f"<{filename}>\n" # Add newline after start tag for readability
                        end_tag = f"\n</{filename}>\n\n" # Add newlines before/after end tag for separation

                        try:
                            # Open and read the content of the source file with UTF-8 encoding
                            with open(filepath, 'r', encoding='utf-8') as infile:
                                content = infile.read()

                            # Write the tagged content to the output file
                            outfile.write(start_tag)
                            outfile.write(content)
                            # Ensure content ends with a newline if it doesn't, before the end tag
                            if not content.endswith('\n'):
                                outfile.write('\n')
                            outfile.write(end_tag)

                        except FileNotFoundError:
                            print(f"    Warning: File {filename} not found unexpectedly. Skipping.")
                        except UnicodeDecodeError:
                            print(f"    Warning: Could not decode {filename} using UTF-8. Skipping.")
                            # Optional: Try other encodings like 'gbk' or 'latin-1' if needed
                            # try:
                            #     with open(filepath, 'r', encoding='gbk') as infile:
                            #         content = infile.read()
                            #     # ... write content ...
                            # except Exception as decode_err:
                            #      print(f"    Error: Failed to decode {filename} with fallback encoding: {decode_err}")
                        except Exception as e:
                            print(f"    Error reading file {filename}: {e}. Skipping.")

        if files_processed_count > 0:
            print(f"\nSuccessfully processed {files_processed_count} files.")
            print(f"Combined output saved to: {output_filepath}")
        else:
            print("\nNo matching files (.py, .yml, README.md) found in the directory.")
            # Optionally remove the empty output file if no files were processed
            try:
                os.remove(output_filepath)
                print(f"Removed empty output file: {output_filepath}")
            except OSError:
                pass # Ignore error if file couldn't be removed (e.g., permissions)

    except IOError as e:
        print(f"\nError opening or writing to output file {output_filepath}: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

# --- How to use the script ---
if __name__ == "__main__":
    # Run the function to combine files in the script's directory
    combine_files_to_txt()

    # Example: To specify a different output filename and target directory:
    # combine_files_to_txt(output_filename="my_combined_code.txt", target_directory="/path/to/your/project")