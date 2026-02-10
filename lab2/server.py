import socket
import hashlib

HOST = '127.0.0.1'
PORT = 65432
CSV_FILE = "course_grades.csv"

# Command constants
GET_MIDTERM_AVG_CMD = "GMA"
GET_LAB_1_AVG_CMD = "GL1A"
GET_LAB_2_AVG_CMD = "GL2A"
GET_LAB_3_AVG_CMD = "GL3A"
GET_LAB_4_AVG_CMD = "GL4A"

COMMANDS = {
    GET_MIDTERM_AVG_CMD: "Midterm",
    GET_LAB_1_AVG_CMD: "Lab 1",
    GET_LAB_2_AVG_CMD: "Lab 2",
    GET_LAB_3_AVG_CMD: "Lab 3",
    GET_LAB_4_AVG_CMD: "Lab 4",
}


class Server:

    def __init__(self):
        self.records = []
        self.hashed_credentials = {}
        self.csv_file = CSV_FILE
        self.import_grade_database()

    def import_grade_database(self):
        self.read_and_clean_database_records()
        self.parse_student_records()
        self.create_hashed_credentials()

    def read_and_clean_database_records(self):
        try:
            file = open(self.csv_file, 'r')
        except FileNotFoundError:
            print(f"Could not find database file {self.csv_file}")
            exit()

        self.cleaned_records = [
            cleaned_line
            for cleaned_line in [line.strip() for line in file.readlines()]
            if cleaned_line != '' and not cleaned_line.startswith("Averages")
        ]
        file.close()

        # Remove header row
        self.cleaned_records = self.cleaned_records[1:]

    def parse_student_records(self):
        print("Data read from CSV file: ")
        try:
            for line in self.cleaned_records:
                elements = [e.strip() for e in line.split(',')]
                record = {
                    'ID Number': elements[0],
                    'Password': elements[1],
                    'Last Name': elements[2],
                    'First Name': elements[3],
                    'Midterm': int(elements[4]),
                    'Lab 1': int(elements[5]),
                    'Lab 2': int(elements[6]),
                    'Lab 3': int(elements[7]),
                    'Lab 4': int(elements[8]),
                }
                self.records.append(record)
                print(record)
        except Exception:
            print("Invalid input file")
            exit()

    def create_hashed_credentials(self):
        for record in self.records:
            h = hashlib.sha256()
            h.update(record['ID Number'].encode('utf-8'))
            h.update(record['Password'].encode('utf-8'))
            self.hashed_credentials[h.digest()] = record

    def compute_average(self, field):
        total = sum(r[field] for r in self.records)
        return total / len(self.records)

    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen()
            print(f"Listening for connections on port {PORT}.")

            while True:
                conn, addr = s.accept()
                with conn:
                    print(f"Connection received from {addr[0]} on port {addr[1]}.")
                    data = conn.recv(1024)
                    if not data:
                        continue

                    # Try to decode as a command string
                    try:
                        decoded = data.decode('utf-8')
                        if decoded in COMMANDS:
                            field = COMMANDS[decoded]
                            avg = self.compute_average(field)
                            print(f"Received {decoded} command from client.")
                            response = f"{field} Average: {avg:.1f}"
                            conn.sendall(response.encode('utf-8'))
                            continue
                    except UnicodeDecodeError:
                        pass

                    # Otherwise treat as ID/password hash
                    print(f"Received ID/password hash {data.hex()} from client.")
                    if data in self.hashed_credentials:
                        record = self.hashed_credentials[data]
                        print("Correct password, record found.")
                        response = (
                            f"Midterm: {record['Midterm']}, "
                            f"Lab 1: {record['Lab 1']}, "
                            f"Lab 2: {record['Lab 2']}, "
                            f"Lab 3: {record['Lab 3']}, "
                            f"Lab 4: {record['Lab 4']}"
                        )
                        conn.sendall(response.encode('utf-8'))
                    else:
                        print("Password failure.")
                        conn.sendall("Password failure.".encode('utf-8'))


def main():
    server = Server()
    server.run()


if __name__ == "__main__":
    main()
