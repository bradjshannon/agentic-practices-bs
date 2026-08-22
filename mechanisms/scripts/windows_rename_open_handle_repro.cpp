#include <fcntl.h>
#include <io.h>
#include <sys/stat.h>
#include <share.h>
#include <cstdio>
#include <filesystem>
namespace fs = std::filesystem;
int main() {
    fs::remove("a.tmp");
    fs::remove("b.tmp");
    int fd = -1;
    _sopen_s(&fd, "a.tmp", _O_RDWR|_O_CREAT|_O_APPEND|_O_BINARY, _SH_DENYNO, _S_IREAD|_S_IWRITE);
    printf("open fd=%d\n", fd);
    const char buf[4] = {1,2,3,4};
    _write(fd, buf, 4);
    _commit(fd);
    // Attempt rename WHILE fd is still open (mirrors persist_state's order)
    std::error_code ec;
    fs::rename("a.tmp", "b.tmp", ec);
    printf("rename-while-open: ec=%d (%s)\n", ec.value(), ec.message().c_str());
    _close(fd);
    std::error_code ec2;
    fs::rename("a.tmp", "b.tmp", ec2);
    printf("rename-after-close: ec=%d (%s)\n", ec2.value(), ec2.message().c_str());
    return 0;
}
