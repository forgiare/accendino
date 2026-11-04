#include <QCoreApplication>
#include <QWebSocket>
#include <cstdio>

int main(int argc, char *argv[]) {
    QCoreApplication app(argc, argv);
    QWebSocket socket;
    std::printf("hello from Qt %s\n", qVersion());
    return 0;
}
