#!/bin/make
# Makefile for compiled programs in this directory.
# By Rein Ytterberg 2022-03-09

CC=cc -Wall

GCC=g++

ALL:    snakesrv snake++srv

snakesrv: snakesrv.o
	$(CC) $^ -o $@

snakesrv.o: snakesrv.c
	$(CC) -c $^


snake++srv: snake++srv.o
	$(GCC) $^ -o $@

snake++srv.o: snake++srv.cpp
	$(GCC) -c $^
