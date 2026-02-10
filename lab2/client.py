import socket
import hashlib
import getpass

HOST = '127.0.0.1'
PORT = 65432

# Command constants
GET_MIDTERM_AVG_CMD = "GMA"
GET_LAB_1_AVG_CMD = "GL1A"
GET_LAB_2_AVG_CMD = "GL2A"
GET_LAB_3_AVG_CMD = "GL3A"
GET_LAB_4_AVG_CMD = "GL4A"
GET_GRADES_CMD = "GG"

AVG_COMMANDS = {
    GET_MIDTERM_AVG_CMD: "Fetching Midterm average:",
    GET_LAB_1_AVG_CMD: "Fetching Lab 1 average:",
    GET_LAB_2_AVG_CMD: "Fetching Lab 2 average:",
    GET_LAB_3_AVG_CMD: "Fetching Lab 3 average:",
    GET_LAB_4_AVG_CMD: "Fetching Lab 4 average:",
}

class Client:

    def run(self):
        while True:
            cmd = input("Enter a command (GMA, GL1A, GL2A, GL3A, GL4A, GG): ")
            print(f"Command entered: {cmd}")

            if cmd in AVG_COMMANDS:
                self.get_average(cmd)
            elif cmd == GET_GRADES_CMD:
                self.get_grades()
            else:
                print("Invalid command.")

    def get_average(self, cmd):
        print(AVG_COMMANDS[cmd])
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            s.sendall(cmd.encode('utf-8'))
            data = s.recv(1024)
            print(data.decode('utf-8'))

    def get_grades(self):
        student_id = input("Enter student ID: ")
        password = getpass.getpass("Enter password: ")
        print(f"ID number {student_id} and password {password} received.")

        h = hashlib.sha256()
        h.update(student_id.encode('utf-8'))
        h.update(password.encode('utf-8'))
        hash_digest = h.digest()
        print(f"ID/password hash {hash_digest.hex()} sent to server.")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            s.sendall(hash_digest)
            data = s.recv(1024)
            print(data.decode('utf-8'))


def main():
    client = Client()
    client.run()


if __name__ == "__main__":
    main()
