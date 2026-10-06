/* Ejecutable portátil: incluye el paquete, lo extrae y abre la interfaz. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static int wait_child(pid_t pid) {
    int status;
    while (waitpid(pid, &status, 0) == -1) {
        if (errno != EINTR) return 1;
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}

static void cleanup(const char *folder) {
    pid_t pid = fork();
    if (pid == 0) {
        execlp("rm", "rm", "-rf", "--", folder, (char *)NULL);
        _exit(127);
    }
    if (pid > 0) wait_child(pid);
}

int main(int argc, char **argv) {
    if (argc > 1 && strcmp(argv[1], "--ayuda") == 0) {
        puts("Restaurador Fotográfico · Fedora 44 x86_64\n"
             "Sin argumentos: abre la aplicación gráfica.\n"
             "--instalar: instala el programa para tu usuario.\n"
             "--verificar: comprueba motor, dependencias e interfaz.\n"
             "También puedes pasar la ruta de una fotografía.");
        return 0;
    }
    int fd = open("/proc/self/exe", O_RDONLY);
    unsigned char footer[16];
    off_t total = fd >= 0 ? lseek(fd, 0, SEEK_END) : -1;
    if (total < 16 || lseek(fd, total-16, SEEK_SET) < 0 || read(fd, footer, 16) != 16 ||
        memcmp(footer, "RFOTO001", 8) != 0) {
        fputs("El ejecutable está incompleto o dañado.\n", stderr);
        if (fd >= 0) close(fd);
        return 1;
    }
    uint64_t offset = 0;
    for (int i = 0; i < 8; i++) offset |= (uint64_t)footer[8+i] << (8*i);
    if (offset >= (uint64_t)total-16 || lseek(fd, (off_t)offset, SEEK_SET) < 0) {
        close(fd); return 1;
    }
    char folder[] = "/tmp/restaurador-portable.XXXXXX";
    if (!mkdtemp(folder)) {
        perror("No se pudo crear la carpeta temporal"); close(fd); return 1;
    }
    int channel[2];
    if (pipe(channel) < 0) { close(fd); cleanup(folder); return 1; }
    pid_t unpack = fork();
    if (unpack == 0) {
        close(channel[1]); close(fd);
        if (dup2(channel[0], STDIN_FILENO) < 0) _exit(126);
        close(channel[0]);
        execlp("tar", "tar", "--no-same-owner", "-xz", "-C", folder, (char *)NULL);
        perror("No se pudo ejecutar tar"); _exit(127);
    }
    if (unpack < 0) {
        close(fd); close(channel[0]); close(channel[1]); cleanup(folder); return 1;
    }
    close(channel[0]);
    signal(SIGPIPE, SIG_IGN);
    unsigned char buffer[131072];
    uint64_t remaining = (uint64_t)total-16-offset;
    int failed = 0;
    while (remaining) {
        size_t amount = remaining < sizeof(buffer) ? (size_t)remaining : sizeof(buffer);
        ssize_t got = read(fd, buffer, amount);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) { failed = 1; break; }
        ssize_t sent = 0;
        while (sent < got) {
            ssize_t n = write(channel[1], buffer+sent, (size_t)(got-sent));
            if (n < 0 && errno == EINTR) continue;
            if (n <= 0) { failed = 1; break; }
            sent += n;
        }
        if (failed) break;
        remaining -= (uint64_t)got;
    }
    close(fd); close(channel[1]);
    int unpack_status = wait_child(unpack);
    if (failed || unpack_status) {
        fputs("No se pudo extraer el programa. Comprueba el espacio en /tmp.\n", stderr);
        cleanup(folder); return 1;
    }
    int install = argc > 1 && strcmp(argv[1], "--instalar") == 0;
    char entry[512];
    snprintf(entry, sizeof(entry), "%s/Restaurador_Fotografico_Fedora/%s", folder,
             install ? "instalar.sh" : "abrir.sh");
    char **args = calloc((size_t)argc+2, sizeof(char *));
    if (!args) { cleanup(folder); return 1; }
    args[0] = "/bin/bash";
    args[1] = entry;
    if (!install) for (int i=1; i<argc; i++) args[i+1] = argv[i];
    pid_t app = fork();
    if (app == 0) {
        execv(args[0], args);
        perror("No se pudo iniciar la aplicación"); _exit(127);
    }
    int result = app > 0 ? wait_child(app) : 1;
    free(args);
    cleanup(folder);
    return result;
}
