#include <stdio.h>
#include <stdlib.h>
#include "hello.pb-c.h"

int main(void)
{
	Hello h = HELLO__INIT;
	h.name = "accendino";
	h.id = 42;

	size_t len = hello__get_packed_size(&h);
	uint8_t* buf = malloc(len);
	if (!buf)
		return 1;
	hello__pack(&h, buf);

	Hello* d = hello__unpack(NULL, len, buf);
	free(buf);
	if (!d)
		return 1;

	printf("%s %d\n", d->name, d->id);
	hello__free_unpacked(d, NULL);
	return 0;
}
