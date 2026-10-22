#include <iostream>
#include "hello.pb.h"

int main()
{
	Hello h;
	h.set_name("accendino");
	h.set_id(42);

	Hello d;
	if (!d.ParseFromString(h.SerializeAsString()))
		return 1;

	std::cout << d.name() << " " << d.id() << std::endl;
	return 0;
}
