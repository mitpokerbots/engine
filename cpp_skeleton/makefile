SOURCES = main.cpp player.cpp skeleton/runner.cpp skeleton/states.cpp skeleton/actions.cpp
HEADERS = player.hpp skeleton/bot.hpp skeleton/runner.hpp skeleton/states.hpp skeleton/actions.hpp

CXX = g++
CXXFLAGS = -Wall -std=c++11
LDLIBS = -lboost_system -lpthread

cppbot: $(SOURCES) $(HEADERS)
	$(CXX) $(CXXFLAGS) -o cppbot $(SOURCES) $(LDLIBS)

clean:
	rm cppbot