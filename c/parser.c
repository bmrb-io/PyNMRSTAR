#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdbool.h>

// Our whitepspace chars
char whitespace[4] = " \n\t\v";

// A parser struct to keep track of state
typedef struct {
    const char * source;
    char * full_data;
    char * token;
    long index;
    long line_no;
    long length;
    char last_delineator;
} parser_data;

//void PyErr_SetString(void);


void reset_parser(parser_data * parser){
    parser->source = NULL;
    free(parser->full_data);
    parser->full_data = NULL;
    free(parser->token);
    parser->token = NULL;
    parser->index = 0;
    parser->length = 0;
    parser->last_delineator = 0;
}

void print_parser_state(parser_data * parser){
    if (parser->source){
        printf("parser(%s):\n", parser->source);
    } else {
        printf("parser(NULL)\n");
        return;
    }
    printf(" Pos: %lu/%lu\n", parser->index, parser->length);
    printf(" Last delim: '%c'\n", parser->last_delineator);
    printf(" Last token: '%s'\n\n", parser->token);
}

/* Return the index of the first match of needle in haystack, or -1 */
long index_handle(char * haystack, char * needle, long start_pos){

    haystack += sizeof(char) * start_pos;
    char * start = strstr(haystack, needle);

    // Word not found
    if (!start){
        return -1;
    }

    // Calculate length into start is new word
    long diff = start - haystack;
    return diff;
}

void get_file(const char *fname, parser_data * parser){
    printf("Parsing: %s\n", fname);

    // Open the file
    FILE *f = fopen(fname, "rb");
    if (!f){
        //PyErr_SetString(PyExc_IOError, "Could not open file.");
        printf("Could not open file.");
        return;
    }

    // Determine how long it is
    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);

    // Allocate space for the file in RAM and load the file
    char *string = malloc(fsize + 1);
    if (fread(string, fsize, 1, f) != 1){
        //PyErr_SetString(PyExc_IOError, "Short read of file.");
        printf("File read error.");
        return;
    }

    fclose(f);
    // Zero terminate
    string[fsize] = 0;

    parser->full_data = string;
    parser->length = fsize;
    parser->source = fname;
    parser->index = 0;
    parser->last_delineator = 0;
    parser->line_no = 0;
}



/* Determines if a character is whitespace */
bool is_whitespace(char test){
    for (int x; x<sizeof(whitespace); x++){
        if (test == whitespace[x]){
            return true;
        }
    }
    return false;
}

/* Returns the index of the next whitespace in the string. */
long get_next_whitespace(char * string, long start_pos){

    long pos = start_pos;
    while (string[pos] != '\0'){
        if (is_whitespace(string[pos])){
            return pos;
        }
        pos++;
    }
    return pos;
}

char * get_token(parser_data * parser){

    // Free the existing token
    free(parser->token);

    for (long x = parser->index; x < parser->length; x++){
        // Keep track of the line number during tokenizing
        if (parser->full_data[x] == '\n'){
            parser->line_no++;
        }

        // See if the character is whitespace
        if (is_whitespace(parser->full_data[x])){
            long token_size = x - parser->index;
            parser->token = malloc(token_size+1);
            memcpy(parser->token, &parser->full_data[parser->index], token_size);
            parser->token[token_size] = '\0';
            parser->index = x + 1;
            parser->last_delineator = parser->full_data[x];
            return parser->token;
        }
    }

    // Last token
    long token_size = parser->length - parser->index;
    if (token_size == 0){
        parser->token = NULL;
    } else {
        parser->token = malloc(token_size+1);
        memcpy(parser->token, &parser->full_data[parser->index], token_size);
        parser->token[token_size] = '\0';
    }
    parser->index = parser->length;
    return parser->token;
}

// Get the current line number
long get_line_number(parser_data * parser){
    long num_lines = 0;
    for (long x = 0; x < parser->index; x++){
        if (parser->full_data[x] == '\n'){
            num_lines++;
        }
    }
    return num_lines;
}

int main(int argc, char *argv[]){

    // Initialize the parser
    parser_data parser = {NULL, NULL, NULL, 0, 0, 0, 0};

    // Read the file
    get_file(argv[1], &parser);

    // Print the tokens
    while(parser.index < parser.length){
        get_token(&parser);
        //printf("Token (%lu): %s\n", get_line_number(&parser), parser.token);
        //printf("Token: %s\n", parser.token);
    }
    reset_parser(&parser);
}
