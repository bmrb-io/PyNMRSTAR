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

// Initialize the parser
parser_data parser = {NULL, NULL, (void *)1, 0, 0, 0, 0};

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
long get_index(char * haystack, char * needle, long start_pos){

    haystack += sizeof(char) * start_pos;
    char * start = strstr(haystack, needle);

    // Return the end if string not found
    if (!start){
        return strlen(haystack) - start_pos;
    }

    // Calculate the length into start is the new word
    long diff = start - haystack;
    return diff;
}

void get_file(const char *fname, parser_data * parser){
    //printf("Parsing: %s\n", fname);

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

/* Scan the index to the next non-whitespace char */
void pass_whitespace(parser_data * parser){

    //printf("Scan from %ld\n", parser->index);
    while ((parser->index < parser->length) &&
            (is_whitespace(parser->full_data[parser->index]))){
        parser->index++;
    }
    //printf("Scan to %ld\n", parser->index);
}

/* Determines if we are done parsing. */
bool check_finished(parser_data * parser){
    if (parser->index == parser->length){
        free(parser->token);
        parser->token = NULL;
        return true;
    }
    return false;
}

/* Returns a new token char * */
char * update_token(parser_data * parser, long length){

    if (parser->token != (void *)1){
        free(parser->token);
    }
    parser->token = malloc(length+1);
    memcpy(parser->token, &parser->full_data[parser->index], length);
    parser->token[length] = '\0';

    // Figure out what to set the last delineator as
    if (parser->index == 0){
        parser->last_delineator = 's';
    } else {
        char ld = parser->full_data[parser->index-1];
        if ((ld == '\n') && (parser->index > 2) && (parser->full_data[parser->index-2] == ';')){
            parser->last_delineator = ';';
        } else if ((ld == '"') || (ld == '\'')){
            parser->last_delineator = ld;
        } else {
            parser->last_delineator = ' ';
        }
    }

    parser->index += length + 1;
    return parser->token;
}

char * get_token(parser_data * parser){

    // Reset the delineator
    parser->last_delineator = '\0';

    // Set up a tmp str pointer to use for searches
    char * search;

    // Nothing left
    if (parser->token == NULL){
        return parser->token;
    }

    // We're at the end if the index is the length
    if (parser->index >= parser->length){
        parser->token = NULL;
        return parser->token;
    }

    // Skip whitespace
    pass_whitespace(parser);

    // Stop if we are at the end
    if (check_finished(parser)){
        parser->token = NULL;
        return parser->token;
    }

    // See if this is a comment - if so skip it
    if (parser->full_data[parser->index] == '#'){
        search = "\n";
        //printf("Skipping comment of length: %ld\n", get_index(parser->full_data, search, parser->index));
        parser->index += get_index(parser->full_data, search, parser->index);
        return get_token(parser);
    }

    // See if this is a multiline comment
    if ((parser->length - parser->index > 1) && (parser->full_data[parser->index] == ';') && (parser->full_data[parser->index+1] == '\n')){
        //printf("Multiline\n");
        search = "\n;";
        long length = get_index(parser->full_data, search, parser->index);
        parser->index += 2;
        return update_token(parser, length-1);
    }

    // Handle values quoted with '
    if (parser->full_data[parser->index] == '\''){
        search = "'";
        long end_quote = get_index(parser->full_data, search, parser->index + 1);

        //TODO ERROR no terminating quote
        //"Invalid file. Single quoted value was never "
                                 //"terminated."
        if (parser->index + end_quote == parser->length){
            parser->index = parser->length;
            parser->token = NULL;
            return parser->token;
        }

        // Make sure we don't stop for quotes that are not followed by whitespace
        while ((parser->index+end_quote+2 < parser->length) && (!is_whitespace(parser->full_data[parser->index+end_quote+2]))){
            end_quote += get_index(parser->full_data, search, parser->index+end_quote+2) + 1;
        }

        // Move the index 1 to skip the '
        parser->index++;
        return update_token(parser, end_quote);
    }

    // Handle values quoted with "
    if (parser->full_data[parser->index] == '\"'){
        search = "\"";
        long end_quote = get_index(parser->full_data, search, parser->index + 1);

        //TODO ERROR no terminating quote
        //"Invalid file. Double quoted value was never "
                                 //"terminated."
        if (parser->index + end_quote == parser->length){
            parser->index = parser->length;
            parser->token = NULL;
            return parser->token;
        }

        // Make sure we don't stop for quotes that are not followed by whitespace
        while ((parser->index+end_quote+2 < parser->length) && (!is_whitespace(parser->full_data[parser->index+end_quote+2]))){
            end_quote += get_index(parser->full_data, search, parser->index+end_quote+2) + 1;
        }

        // Move the index 1 to skip the "
        parser->index++;
        return update_token(parser, end_quote);
    }

    // Nothing special. Just get the token
    long end_pos = get_next_whitespace(parser->full_data, parser->index);
    return update_token(parser, end_pos - parser->index);
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

    // Read the file
    get_file(argv[1], &parser);

    // Print the tokens
    while(get_token(&parser) != NULL){
        //printf("Token (%lu): %s\n", get_line_number(&parser), parser.token);
        printf("Token (%c): %s\n", parser.last_delineator, parser.token);
    }
    reset_parser(&parser);
}
