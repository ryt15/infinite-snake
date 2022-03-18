#!/bin/make
# Makefile for compiled programs in this directory.
# By Rein Ytterberg 2022-03-09

CC=cc

GCC=g++

ALL=snakesrv

snakesrv: snakesrv.o
	$(CC) $^ -o $@

snakesrv.o: snakesrv.c
	$(CC) -c $^
